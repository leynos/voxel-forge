"""MagicaVoxel .vox import/export (Goxel-compatible format)."""

from __future__ import annotations

import struct
from pathlib import Path

from .mesh_merge import merge_scene
from .model import VoxelScene

VOX_MAGIC = b"VOX "
VERSION = 150

_HEADER_SIZE = 8  # magic + version
_CHUNK_ID_SIZE = 4
_CHUNK_HEADER_SIZE = 12  # identifier + content size + children size
_PALETTE_ENTRIES = 256
_MAX_PALETTE_COLOURS = 255
_RGBA_CHUNK_BYTES = _PALETTE_ENTRIES * 4
_XYZI_COUNT_BYTES = 4
_XYZI_RECORD_BYTES = 4
_CHANNEL_MAX = 255
_MAX_AXIS_EXTENT = 256
_BOX_VERTEX_COUNT = 8
_BOX_FACES = (
    (1, 2, 3, 4),
    (5, 6, 7, 8),
    (1, 2, 6, 5),
    (2, 3, 7, 6),
    (3, 4, 8, 7),
    (4, 1, 5, 8),
)


class _VoxContents:
    """Palette entries and voxels accumulated while parsing a ``.vox`` file."""

    def __init__(self) -> None:
        self.palette: list[tuple[int, int, int]] = [(0, 0, 0)] * _PALETTE_ENTRIES
        self.voxels: list[tuple[int, int, int, int]] = []
        self.has_rgba = False


def _read_rgba_chunk(content: bytes, contents: _VoxContents) -> None:
    """Read a palette chunk into ``contents``.

    Raises
    ------
    ValueError
        If the chunk holds fewer bytes than a full palette.

    """
    if len(content) < _RGBA_CHUNK_BYTES:
        msg = "RGBA chunk is truncated"
        raise ValueError(msg)
    contents.has_rgba = True
    for entry_index in range(_MAX_PALETTE_COLOURS):
        red, green, blue, _alpha = struct.unpack_from("<4B", content, entry_index * 4)
        contents.palette[entry_index + 1] = (red, green, blue)


def _read_xyzi_chunk(content: bytes, contents: _VoxContents) -> None:
    """Read a complete voxel chunk into ``contents``.

    Raises
    ------
    ValueError
        If the count header or a declared voxel record is truncated.

    """
    msg = "XYZI chunk is truncated"
    if len(content) < _XYZI_COUNT_BYTES:
        raise ValueError(msg)
    count = struct.unpack_from("<I", content, 0)[0]
    if len(content) < _XYZI_COUNT_BYTES + count * _XYZI_RECORD_BYTES:
        raise ValueError(msg)
    for index in range(count):
        offset = _XYZI_COUNT_BYTES + index * _XYZI_RECORD_BYTES
        x, y, z, colour_index = struct.unpack_from("<4B", content, offset)
        contents.voxels.append((x, y, z, colour_index))


def _parse_chunks(data: bytes, pos: int, contents: _VoxContents) -> int:
    """Walk the chunk tree from ``pos``, returning the offset reached."""
    while pos < len(data):
        chunk_id = data[pos : pos + _CHUNK_ID_SIZE]
        if len(chunk_id) < _CHUNK_ID_SIZE:
            break
        content_size = struct.unpack_from("<I", data, pos + 4)[0]
        children_size = struct.unpack_from("<I", data, pos + 8)[0]
        content_start = pos + _CHUNK_HEADER_SIZE
        content = data[content_start : content_start + content_size]
        child_start = content_start + content_size

        match chunk_id:
            case b"RGBA":
                _read_rgba_chunk(content, contents)
            case b"XYZI":
                _read_xyzi_chunk(content, contents)

        if children_size:
            _parse_chunks(data, child_start, contents)
            pos = child_start + children_size
        else:
            pos = child_start
    return pos


def import_vox(path: str | Path) -> VoxelScene:
    """Load a MagicaVoxel ``.vox`` file into a scene.

    Parameters
    ----------
    path : str | Path
        Location of the ``.vox`` file to read.

    Returns
    -------
    VoxelScene
        Scene holding the file's palette and voxels, named after the file stem.

    Raises
    ------
    ValueError
        If the file does not begin with the ``VOX `` magic bytes.

    """
    path = Path(path)
    data = path.read_bytes()
    if data[: len(VOX_MAGIC)] != VOX_MAGIC:
        msg = "not a valid .vox file"
        raise ValueError(msg)

    scene = VoxelScene(name=path.stem)
    scene.layers.clear()

    contents = _VoxContents()
    _parse_chunks(data, _HEADER_SIZE, contents)

    if contents.has_rgba:
        for colour_index in range(1, _PALETTE_ENTRIES):
            scene.palette[str(colour_index)] = contents.palette[colour_index]

    layer = scene.layers[0] if scene.layers else scene.add_layer("Layer 1")
    for x, y, z, colour_index in contents.voxels:
        layer.blocks[x, y, z] = str(colour_index)

    return scene


def _voxel_extent(
    blocks: list[tuple[int, int, int, str, str]],
) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    """Return the minimum corner and the size of a block set's bounding box."""
    if not blocks:
        return (0, 0, 0), (1, 1, 1)
    mins = (
        min(block[0] for block in blocks),
        min(block[1] for block in blocks),
        min(block[2] for block in blocks),
    )
    sizes = (
        max(block[0] for block in blocks) - mins[0] + 1,
        max(block[1] for block in blocks) - mins[1] + 1,
        max(block[2] for block in blocks) - mins[2] + 1,
    )
    return mins, sizes


def _reject_oversize(sizes: tuple[int, int, int]) -> None:
    """Reject extents that VOX version 150 cannot address.

    Raises
    ------
    ValueError
        If any axis needs more than 256 voxels.

    """
    if any(size > _MAX_AXIS_EXTENT for size in sizes):
        msg = "VOX version 150 supports a maximum size of 256 voxels on each axis"
        raise ValueError(msg)


def _encode_voxels(
    scene: VoxelScene,
    blocks: list[tuple[int, int, int, str, str]],
    origin: tuple[int, int, int],
) -> tuple[list[tuple[int, int, int, int]], list[tuple[int, int, int, int]]]:
    """Translate blocks to ``origin`` and index their colours into a palette.

    Parameters
    ----------
    scene : VoxelScene
        Scene supplying the colour lookup.
    blocks : list
        Blocks as returned by :meth:`VoxelScene.all_blocks`.
    origin : tuple[int, int, int]
        Corner subtracted from every block so the output starts at zero.

    Returns
    -------
    tuple
        The translated voxels and the 256-entry RGBA palette.

    Raises
    ------
    ValueError
        If the scene needs more than 255 distinct colours.

    """
    palette: list[tuple[int, int, int, int]] = [(0, 0, 0, 0)] * _PALETTE_ENTRIES
    colour_indices: dict[tuple[int, int, int], int] = {}
    occupied: set[tuple[int, int, int]] = set()
    encoded: list[tuple[int, int, int, int]] = []
    for block in blocks:
        coordinate = block[:3]
        if coordinate in occupied:
            msg = "VOX version 150 cannot represent overlapping visible-layer voxels"
            raise ValueError(msg)
        occupied.add(coordinate)
        rgb = scene.resolve_color(block[3])
        colour_index = colour_indices.get(rgb)
        if colour_index is None:
            colour_index = len(colour_indices) + 1
            if colour_index > _MAX_PALETTE_COLOURS:
                msg = "VOX version 150 supports at most 255 colours"
                raise ValueError(msg)
            colour_indices[rgb] = colour_index
            palette[colour_index - 1] = (*rgb, _CHANNEL_MAX)
        encoded.append((
            block[0] - origin[0],
            block[1] - origin[1],
            block[2] - origin[2],
            colour_index,
        ))
    return encoded, palette


def _pack_chunk(chunk_id: bytes, content: bytes) -> bytes:
    """Frame one childless VOX chunk."""
    return chunk_id + struct.pack("<I", len(content)) + struct.pack("<I", 0) + content


def _pack_xyzi(blocks: list[tuple[int, int, int, int]]) -> bytes:
    """Serialise translated voxels as an XYZI chunk body."""
    packed = b"".join(struct.pack("<4B", *block) for block in blocks)
    return struct.pack("<I", len(blocks)) + packed


def _pack_rgba(palette: list[tuple[int, int, int, int]]) -> bytes:
    """Serialise a palette as an RGBA chunk body."""
    return b"".join(struct.pack("<4B", *entry) for entry in palette)


def export_vox(scene: VoxelScene, path: str | Path) -> Path:
    """Write a scene as a MagicaVoxel ``.vox`` file.

    Parameters
    ----------
    scene : VoxelScene
        Scene to serialise.
    path : str | Path
        Destination file; missing parent directories are created.

    Returns
    -------
    Path
        The path that was written.

    Raises
    ------
    ValueError
        If the scene exceeds 256 voxels on an axis or needs over 255 colours.

    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    blocks = scene.all_blocks()
    origin, sizes = _voxel_extent(blocks)
    _reject_oversize(sizes)
    encoded_blocks, palette = _encode_voxels(scene, blocks, origin)

    main_children = (
        _pack_chunk(b"SIZE", struct.pack("<III", *sizes))
        + _pack_chunk(b"XYZI", _pack_xyzi(encoded_blocks))
        + _pack_chunk(b"RGBA", _pack_rgba(palette))
    )
    main_chunk = (
        b"MAIN"
        + struct.pack("<I", 0)
        + struct.pack("<I", len(main_children))
        + main_children
    )

    path.write_bytes(VOX_MAGIC + struct.pack("<I", VERSION) + main_chunk)
    return path


def _box_vertices(
    corner_min: tuple[int, int, int],
    corner_max: tuple[int, int, int],
    voxel_size: float,
) -> list[tuple[float, float, float]]:
    """Return the eight corners of one box, in world units."""
    ox, oy, oz = (value * voxel_size for value in corner_min)
    sx, sy, sz = (
        (corner_max[axis] - corner_min[axis] + 1) * voxel_size for axis in range(3)
    )
    return [
        (ox, oy, oz),
        (ox + sx, oy, oz),
        (ox + sx, oy + sy, oz),
        (ox, oy + sy, oz),
        (ox, oy, oz + sz),
        (ox + sx, oy, oz + sz),
        (ox + sx, oy + sy, oz + sz),
        (ox, oy + sy, oz + sz),
    ]


def _box_obj_lines(
    scene: VoxelScene,
    item: tuple[tuple[int, int, int], tuple[int, int, int], str, str],
    vertex_offset: int,
) -> list[str]:
    """Return the comment, vertex and face lines describing one box."""
    corner_min, corner_max, colour, tag = item
    rgb = scene.resolve_color(colour)
    lines = [
        (
            f"# {tag} ({corner_min[0]},{corner_min[1]},{corner_min[2]})"
            f"-({corner_max[0]},{corner_max[1]},{corner_max[2]}) rgb={rgb}"
        )
    ]
    lines.extend(
        f"v {vx} {vy} {vz}"
        for vx, vy, vz in _box_vertices(corner_min, corner_max, scene.voxel_size)
    )
    lines.extend(
        "f " + " ".join(str(vertex_offset + index - 1) for index in face)
        for face in _BOX_FACES
    )
    return lines


def export_obj(
    scene: VoxelScene, path: str | Path, *, merge_boxes: bool = True
) -> Path:
    """Export as Wavefront OBJ, optionally merging adjacent voxels into boxes.

    With ``merge_boxes`` left at its default, touching voxels are merged into
    larger boxes, which is recommended.

    Parameters
    ----------
    scene : VoxelScene
        Scene to serialise.
    path : str | Path
        Destination file; missing parent directories are created.
    merge_boxes : bool
        Merge touching voxels into larger boxes, which is far cheaper to render.

    Returns
    -------
    Path
        The path that was written.

    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = [f"# VoxelForge export — {scene.name}", f"o {scene.name}"]
    if merge_boxes:
        boxes = merge_scene(scene)
        lines.append(
            f"# merged: {len(boxes)} boxes from {sum(b.volume for b in boxes)} voxels"
        )
        items = [
            ((b.x1, b.y1, b.z1), (b.x2, b.y2, b.z2), b.color, "merged") for b in boxes
        ]
    else:
        items = [
            ((x, y, z), (x, y, z), colour, layer)
            for x, y, z, colour, layer in scene.all_blocks()
        ]

    vertex_offset = 1
    for item in items:
        lines.extend(_box_obj_lines(scene, item, vertex_offset))
        vertex_offset += _BOX_VERTEX_COUNT

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
