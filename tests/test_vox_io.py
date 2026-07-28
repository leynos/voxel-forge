from __future__ import annotations

import struct
from pathlib import Path

import pytest

from voxel_forge.model import VoxelScene
from voxel_forge.vox_io import export_vox, import_vox


def child_chunks(data: bytes) -> dict[bytes, bytes]:
    assert data[:4] == b"VOX "
    assert data[8:12] == b"MAIN"
    children_size = struct.unpack_from("<I", data, 16)[0]
    offset = 20
    end = offset + children_size
    chunks: dict[bytes, bytes] = {}
    while offset < end:
        chunk_id = data[offset : offset + 4]
        content_size, nested_size = struct.unpack_from("<II", data, offset + 4)
        content_start = offset + 12
        chunks[chunk_id] = data[content_start : content_start + content_size]
        offset = content_start + content_size + nested_size
    return chunks


def test_export_contains_required_chunks_in_order(tmp_path: Path) -> None:
    scene = VoxelScene("chunks")
    scene.place(2, 3, 4, "2")
    path = export_vox(scene, tmp_path / "chunks.vox")
    data = path.read_bytes()

    assert data.index(b"SIZE") < data.index(b"XYZI") < data.index(b"RGBA")
    chunks = child_chunks(data)
    assert struct.unpack("<III", chunks[b"SIZE"]) == (1, 1, 1)
    assert struct.unpack_from("<I", chunks[b"XYZI"])[0] == 1


def test_export_preserves_hex_colour_through_round_trip(tmp_path: Path) -> None:
    scene = VoxelScene("colour")
    scene.place(0, 0, 0, "#123456")

    loaded = import_vox(export_vox(scene, tmp_path / "colour.vox"))
    colour_key = loaded.layer.blocks[(0, 0, 0)]

    assert loaded.resolve_color(colour_key) == (0x12, 0x34, 0x56)


def test_export_rejects_unrepresentable_dimension(tmp_path: Path) -> None:
    scene = VoxelScene("wide")
    scene.place(0, 0, 0, "1")
    scene.place(256, 0, 0, "1")

    with pytest.raises(ValueError, match="256"):
        export_vox(scene, tmp_path / "wide.vox")
