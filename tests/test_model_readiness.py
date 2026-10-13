"""Executable contract for the readiness gates.

Each test here pins one behaviour that "basic agent-driven voxel scene creation"
depends on: the MCP launcher, bridge scheduling and origin checks, editor
removal round-trips, scene-name and payload validation, resource bounds,
persistence, and the raw structure of exported MagicaVoxel files.

Run the whole module with ``uv run pytest -q``. Tests that touch persistence
request the ``scene_directory`` fixture from ``conftest.py`` so no real
``~/.voxel-forge`` directory is read or written. Assertions carry messages
because a readiness failure should name the broken contract directly.
"""

from __future__ import annotations

import functools
import json
import struct
from pathlib import Path

import pytest
from readiness_helpers import child_chunks

from voxel_forge import scene_store, server
from voxel_forge.model import SceneStore, VoxelScene
from voxel_forge.vox_io import export_vox, import_vox

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_scene_name_cannot_escape_scene_directory(scene_directory: Path) -> None:
    """Saving a traversal-shaped scene name must not write outside its store."""
    scene = VoxelScene("../outside")

    with pytest.raises(ValueError, match="scene name"):
        scene_store.save_scene(scene)

    assert not (scene_directory.parent / "outside.json").exists(), (
        "an unsafe name must not write outside the directory"
    )


def test_unicode_scene_name_round_trips(scene_directory: Path) -> None:
    """Persistence must retain Unicode scene names and their voxel data."""
    scene = VoxelScene("บ้าน เล็ก")
    scene.place(1, 2, 3, "2")

    saved_path = scene_store.save_scene(scene)
    loaded = scene_store.load_scene(scene.name)

    assert saved_path.parent == scene_directory, (
        "a saved scene must stay inside the scenes directory"
    )
    assert loaded.to_dict() == scene.to_dict(), "a saved scene must reload unchanged"


def test_list_saved_scenes_reports_saved_names(scene_directory: Path) -> None:
    """Saved scene names must be returned in sorted order."""
    for name in ("beta", "alpha"):
        scene_store.save_scene(VoxelScene(name))

    assert scene_store.list_saved_scenes() == ["alpha", "beta"], (
        "saved scenes must be listed sorted by name"
    )


def test_list_saved_scenes_leaves_an_absent_store_absent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Listing an absent scene store returns empty without creating it."""
    absent = tmp_path / "never-created"
    monkeypatch.setattr(scene_store, "scenes_dir", lambda: absent)

    listed = scene_store.list_saved_scenes()

    assert listed == [], "an absent store must list as empty rather than failing"
    assert not absent.exists(), (
        "listing must not create the scene directory as a side effect"
    )


@pytest.mark.parametrize(
    "name",
    [
        "",
        ".",
        "..",
        "bad/name",
        "bad\\name",
        "CON",
        "CON.txt",
        "lpt1.scene",
        "trailing.",
    ],
)
def test_scene_store_rejects_unsafe_names(name: str) -> None:
    """Scene creation must reject names that cannot safely identify stored files."""
    store = SceneStore()

    with pytest.raises(ValueError, match="scene name"):
        store.create(name)


def test_store_select_requires_a_registered_scene() -> None:
    """Selection changes the current scene only when the name is registered."""
    store = SceneStore()
    store.create("original")
    store.create("second")

    selected = store.select("original")

    assert selected is store.get(), "select must make the named scene current"
    with pytest.raises(KeyError, match="not loaded in this session"):
        store.select("never-created")


def test_register_makes_a_scene_current() -> None:
    """Registering a scene adopts it as the current scene instance."""
    store = SceneStore()

    registered = store.register(VoxelScene("adopted"))

    assert store.get() is registered, (
        "register must adopt the scene and make it current"
    )


def test_from_dict_rejects_invalid_active_layer() -> None:
    """Deserialisation must reject an active layer outside the scene's layers."""
    data = VoxelScene("valid").to_dict()
    data["active_layer"] = -1

    with pytest.raises(ValueError, match="active_layer"):
        VoxelScene.from_dict(data)


@pytest.mark.parametrize("name", [None, ["a"], {"a": 1}, 7])
def test_from_dict_rejects_non_text_scene_name(name: object) -> None:
    """Deserialisation must reject scene names that are not text."""
    data = VoxelScene("valid").to_dict()
    data["name"] = name

    with pytest.raises(ValueError, match="scene name"):
        VoxelScene.from_dict(data)


def test_place_rejects_unknown_colour_without_mutating_scene() -> None:
    """A rejected colour leaves the scene unchanged."""
    scene = VoxelScene("valid")

    with pytest.raises(ValueError, match="colour"):
        scene.place(0, 0, 0, "not-a-colour")

    assert scene.block_count() == 0, "a rejected placement must not mutate the scene"


def test_basic_agent_scene_workflow(
    empty_server_store: SceneStore,
    monkeypatch: pytest.MonkeyPatch,
    scene_directory: Path,
) -> None:
    """The MCP create, edit, save, and load tools must support one full workflow."""
    assert "basic" in server.voxelforge_create_scene("basic"), (
        "create_scene must name the new scene"
    )
    assert "วาง" in server.voxelforge_place_block(0, 0, 0, "2"), (
        "place_block must confirm the placement"
    )
    assert "เติม" in server.voxelforge_fill_box(1, 2, 0, 0, 0, 0, "3"), (
        "fill_box must confirm the fill"
    )
    assert empty_server_store.get().block_count() == 3, (
        "place_block and fill_box must each add their voxels"
    )
    assert "บันทึก" in server.voxelforge_save(), "save must confirm the file it wrote"

    monkeypatch.setattr(server, "store", SceneStore())
    assert "โหลด" in server.voxelforge_load("basic"), (
        "load must confirm the scene it read"
    )
    assert server.store.get().block_count() == 3, (
        "a reloaded scene must keep its voxels"
    )


def test_export_contains_required_chunks_in_order(tmp_path: Path) -> None:
    """A VOX export must order its chunks and encode visible bounds and count."""
    scene = VoxelScene("chunks")
    scene.place(2, 3, 4, "2")
    path = export_vox(scene, tmp_path / "chunks.vox")
    data = path.read_bytes()

    assert data.index(b"SIZE") < data.index(b"XYZI") < data.index(b"RGBA"), (
        "VOX children must be written SIZE, then XYZI, then RGBA"
    )
    chunks = child_chunks(data)
    assert struct.unpack("<III", chunks[b"SIZE"]) == (1, 1, 1), (
        "SIZE must span the visible bounding box"
    )
    assert struct.unpack_from("<I", chunks[b"XYZI"])[0] == 1, (
        "XYZI must hold one voxel per visible block"
    )


@pytest.mark.parametrize("hex_colour", ["#123456", "#000000"])
def test_export_preserves_hex_colour_through_round_trip(
    tmp_path: Path, hex_colour: str
) -> None:
    """A custom hexadecimal colour must survive export and import."""
    scene = VoxelScene("colour")
    scene.place(0, 0, 0, hex_colour)

    loaded = import_vox(export_vox(scene, tmp_path / "colour.vox"))
    colour_key = loaded.layer.blocks[0, 0, 0]

    assert loaded.resolve_color(colour_key) == scene.resolve_color(hex_colour), (
        "an exported colour must survive a round trip through the palette"
    )


def test_export_rejects_unrepresentable_dimension(tmp_path: Path) -> None:
    """VOX export must reject a dimension that cannot fit its format field."""
    scene = VoxelScene("wide")
    scene.place(0, 0, 0, "1")
    scene.place(256, 0, 0, "1")

    with pytest.raises(ValueError, match="256"):
        export_vox(scene, tmp_path / "wide.vox")


def test_export_rejects_overlapping_visible_layers(tmp_path: Path) -> None:
    """VOX export must reject voxels that overlap across visible layers."""
    scene = VoxelScene("overlap")
    scene.place(0, 0, 0, "1")
    scene.add_layer("upper")
    scene.place(0, 0, 0, "2", layer_index=1)

    with pytest.raises(ValueError, match="overlap"):
        export_vox(scene, tmp_path / "overlap.vox")


@pytest.mark.parametrize("channel", [256, 1.9, True, "1"])
def test_from_dict_rejects_invalid_palette_channels(channel: object) -> None:
    """Reject out-of-range and coercible channels before constructing a scene."""
    data = VoxelScene("valid").to_dict()
    data["palette"] = {"1": [channel, 0, 0]}
    with pytest.raises(ValueError, match="palette"):
        VoxelScene.from_dict(data)


@pytest.mark.parametrize("operation", ["fill", "batch-count", "batch-text"])
def test_bounded_edits_fail_before_mutation(
    empty_server_store: SceneStore, operation: str
) -> None:
    """Enforce count and pre-decode text limits without adding any voxels."""
    scene = empty_server_store.create("bounded")
    error = "at most" if operation == "batch-text" else "100,000"
    match operation:
        case "fill":
            request = functools.partial(
                server.voxelforge_fill_box, 0, 100_000, 0, 0, 0, 0
            )
        case "batch-count":
            blocks = [[index, 0, 0, "1"] for index in range(100_001)]
            request = functools.partial(
                server.voxelforge_place_many, json.dumps(blocks)
            )
        case "batch-text":
            request = functools.partial(
                server.voxelforge_place_many, "[" + "0," * server.MAX_BLOCKS_JSON_CHARS
            )
        case _:
            msg = f"unknown bounded-edit case: {operation}"
            raise ValueError(msg)
    with pytest.raises(ValueError, match=error):
        request()
    assert scene.block_count() == 0, (
        "every rejected bounded edit must leave the scene unchanged"
    )
