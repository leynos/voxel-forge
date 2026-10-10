"""MagicaVoxel .vox import/export (Goxel-compatible format)."""

from __future__ import annotations

import struct
from pathlib import Path

from .mesh_merge import merge_scene
from .model import VoxelScene

VOX_MAGIC = b"VOX "
VERSION = 150


def _read_chunk(f) -> tuple[bytes, bytes, int]:
    chunk_id = f.read(4)
    content_size = struct.unpack("<I", f.read(4))[0]
    children_size = struct.unpack("<I", f.read(4))[0]
    content = f.read(content_size)
    return chunk_id, content, children_size


def import_vox(path: str | Path) -> VoxelScene:
    """
    Read a MagicaVoxel ``.vox`` file into a scene.

    Only the ``SIZE``, ``XYZI`` and ``RGBA`` chunks of a version 150 single-model
    file are consumed; the coordinate origin is preserved as stored in the file
    and no normalisation is applied. When the file carries an ``RGBA`` chunk its
    255 colour entries replace the default palette; otherwise the default
    palette is kept and the imported voxels reference its keys. Every imported
    voxel is placed on the first layer.

    Parameters
    ----------
    path : str | Path
        Path to the ``.vox`` file.

    Returns
    -------
    VoxelScene
        A scene named after the file stem, holding every voxel in the file.

    Raises
    ------
    ValueError
        If the file does not begin with the ``VOX `` magic, or its ``RGBA``
        chunk is truncated.
    OSError
        If the file cannot be read.
    """
    path = Path(path)
    data = path.read_bytes()
    if data[:4] != VOX_MAGIC:
        raise ValueError("ไม่ใช่ไฟล์ .vox ที่ถูกต้อง")

    scene = VoxelScene(name=path.stem)
    scene.layers.clear()

    offset = 8  # magic + version
    palette: list[tuple[int, int, int]] = [(0, 0, 0)] * 256
    voxels: list[tuple[int, int, int, int]] = []
    has_rgba = False

    def parse_at(pos: int, depth: int = 0) -> int:
        nonlocal has_rgba, palette, voxels
        while pos < len(data):
            chunk_id = data[pos : pos + 4]
            if len(chunk_id) < 4:
                break
            content_size = struct.unpack_from("<I", data, pos + 4)[0]
            children_size = struct.unpack_from("<I", data, pos + 8)[0]
            content_start = pos + 12
            content = data[content_start : content_start + content_size]
            child_start = content_start + content_size

            if chunk_id == b"RGBA":
                if len(content) < 1024:
                    raise ValueError("RGBA chunk is truncated")
                has_rgba = True
                for entry_index in range(255):
                    r, g, b, _a = struct.unpack_from("<4B", content, entry_index * 4)
                    palette[entry_index + 1] = (r, g, b)
            elif chunk_id == b"XYZI":
                count = struct.unpack_from("<I", content, 0)[0]
                for i in range(count):
                    x, y, z, ci = struct.unpack_from("<4B", content, 4 + i * 4)
                    voxels.append((x, y, z, ci))

            pos = parse_at(child_start, depth + 1) if children_size else child_start
            if children_size:
                pos = child_start + children_size
            else:
                pos = child_start
            if depth == 0 and pos >= len(data):
                break
        return pos

    parse_at(offset)

    if has_rgba:
        for colour_index in range(1, 256):
            scene.palette[str(colour_index)] = palette[colour_index]

    layer = scene.layers[0] if scene.layers else scene.add_layer("Layer 1")
    for x, y, z, ci in voxels:
        layer.blocks[(x, y, z)] = str(ci)

    return scene


def export_vox(scene: VoxelScene, path: str | Path) -> Path:
    """
    Write a scene as a version 150 MagicaVoxel ``.vox`` file.

    Output is a single-model ``MAIN`` chunk holding ``SIZE``, ``XYZI`` and
    ``RGBA`` children in that order. Coordinates are normalised to the model's
    bounding box, so the file's own origin is the minimum corner of the visible
    voxels. Each distinct visible colour receives a palette index; indices start
    at 1 because index 0 is unused, and index ``n`` maps to palette entry
    ``n - 1``. Hidden layers are omitted.

    Parameters
    ----------
    scene : VoxelScene
        Scene to export. Only visible layers are written.
    path : str | Path
        Destination file. Parent directories are created when absent.

    Returns
    -------
    Path
        The file that was written.

    Raises
    ------
    ValueError
        If any axis of the bounding box exceeds 256 voxels, if more than 255
        distinct colours are visible, or if two visible voxels share a
        coordinate. A ``.vox`` model stores one colour index per coordinate, so
        overlapping visible layers cannot be represented; importing such a file
        would silently drop all but one of the overlapping voxels.
    OSError
        If the destination cannot be written.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    blocks = scene.all_blocks()
    if blocks:
        min_x = min(b[0] for b in blocks)
        min_y = min(b[1] for b in blocks)
        min_z = min(b[2] for b in blocks)
        size_x = max(b[0] for b in blocks) - min_x + 1
        size_y = max(b[1] for b in blocks) - min_y + 1
        size_z = max(b[2] for b in blocks) - min_z + 1
    else:
        min_x = min_y = min_z = 0
        size_x = size_y = size_z = 1

    if any(size > 256 for size in (size_x, size_y, size_z)):
        raise ValueError("VOX version 150 supports a maximum size of 256 voxels on each axis")

    palette = [(0, 0, 0, 0)] * 256
    colour_indices: dict[tuple[int, int, int], int] = {}
    occupied: set[tuple[int, int, int]] = set()
    encoded_blocks: list[tuple[int, int, int, int]] = []
    for x, y, z, colour, _layer in blocks:
        coordinate = (x, y, z)
        if coordinate in occupied:
            raise ValueError("VOX version 150 cannot represent overlapping visible-layer voxels")
        occupied.add(coordinate)
        rgb = scene.resolve_color(colour)
        colour_index = colour_indices.get(rgb)
        if colour_index is None:
            colour_index = len(colour_indices) + 1
            if colour_index > 255:
                raise ValueError("VOX version 150 supports at most 255 colours")
            colour_indices[rgb] = colour_index
            palette[colour_index - 1] = (*rgb, 255)
        encoded_blocks.append((x - min_x, y - min_y, z - min_z, colour_index))

    size_content = struct.pack("<III", size_x, size_y, size_z)
    xyzi_content = struct.pack("<I", len(encoded_blocks))
    xyzi_content += b"".join(struct.pack("<4B", *block) for block in encoded_blocks)

    rgba_content = b"".join(struct.pack("<4B", *p) for p in palette)

    def pack_chunk(chunk_id: bytes, content: bytes) -> bytes:
        return chunk_id + struct.pack("<I", len(content)) + struct.pack("<I", 0) + content

    main_children = (
        pack_chunk(b"SIZE", size_content) + pack_chunk(b"XYZI", xyzi_content) + pack_chunk(b"RGBA", rgba_content)
    )
    main_chunk = b"MAIN" + struct.pack("<I", 0) + struct.pack("<I", len(main_children)) + main_children

    out = VOX_MAGIC + struct.pack("<I", VERSION) + main_chunk
    path.write_bytes(out)
    return path


def export_obj(scene: VoxelScene, path: str | Path, merge_boxes: bool = True) -> Path:
    """Export as Wavefront OBJ. merge_boxes=True รวม voxel ติดกันเป็นกล่องใหญ่ (แนะนำ)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    vs = scene.voxel_size
    lines: list[str] = [f"# VoxelForge export — {scene.name}", f"o {scene.name}"]
    vertex_offset = 1

    if merge_boxes:
        boxes = merge_scene(scene)
        lines.append(f"# merged: {len(boxes)} boxes from {sum(b.volume for b in boxes)} voxels")
        items = [(b.x1, b.y1, b.z1, b.x2, b.y2, b.z2, b.color, "merged") for b in boxes]
    else:
        items = [(x, y, z, x, y, z, color, layer) for x, y, z, color, layer in scene.all_blocks()]

    for x1, y1, z1, x2, y2, z2, color, tag in items:
        rgb = scene.resolve_color(color)
        lines.append(f"# {tag} ({x1},{y1},{z1})-({x2},{y2},{z2}) rgb={rgb}")
        ox, oy, oz = x1 * vs, y1 * vs, z1 * vs
        sx, sy, sz = (x2 - x1 + 1) * vs, (y2 - y1 + 1) * vs, (z2 - z1 + 1) * vs
        verts = [
            (ox, oy, oz),
            (ox + sx, oy, oz),
            (ox + sx, oy + sy, oz),
            (ox, oy + sy, oz),
            (ox, oy, oz + sz),
            (ox + sx, oy, oz + sz),
            (ox + sx, oy + sy, oz + sz),
            (ox, oy + sy, oz + sz),
        ]
        for vx, vy, vz in verts:
            lines.append(f"v {vx} {vy} {vz}")
        faces = [
            (1, 2, 3, 4),
            (5, 6, 7, 8),
            (1, 2, 6, 5),
            (2, 3, 7, 6),
            (3, 4, 8, 7),
            (4, 1, 5, 8),
        ]
        for f in faces:
            lines.append("f " + " ".join(str(vertex_offset + i - 1) for i in f))
        vertex_offset += 8

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
