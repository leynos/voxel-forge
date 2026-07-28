from __future__ import annotations

from pathlib import Path

import pytest

from voxel_forge.model import SceneStore, VoxelScene


def test_scene_name_cannot_escape_scene_directory(scene_directory: Path) -> None:
    scene = VoxelScene("../outside")

    with pytest.raises(ValueError, match="scene name"):
        scene.save()

    assert not (scene_directory.parent / "outside.json").exists()


def test_unicode_scene_name_round_trips(scene_directory: Path) -> None:
    scene = VoxelScene("บ้าน เล็ก")
    scene.place(1, 2, 3, "2")

    saved_path = scene.save()
    loaded = VoxelScene.load(scene.name)

    assert saved_path.parent == scene_directory
    assert loaded.to_dict() == scene.to_dict()


@pytest.mark.parametrize("name", ["", ".", "..", "bad/name", "bad\\name", "CON"])
def test_scene_store_rejects_unsafe_names(name: str) -> None:
    store = SceneStore()

    with pytest.raises(ValueError, match="scene name"):
        store.create(name)


def test_from_dict_rejects_invalid_active_layer() -> None:
    data = VoxelScene("valid").to_dict()
    data["active_layer"] = -1

    with pytest.raises(ValueError, match="active_layer"):
        VoxelScene.from_dict(data)


def test_from_dict_rejects_invalid_palette_channel() -> None:
    data = VoxelScene("valid").to_dict()
    data["palette"] = {"1": [256, 0, 0]}

    with pytest.raises(ValueError, match="palette"):
        VoxelScene.from_dict(data)


def test_place_rejects_unknown_colour_without_mutating_scene() -> None:
    scene = VoxelScene("valid")

    with pytest.raises(ValueError, match="colour"):
        scene.place(0, 0, 0, "not-a-colour")

    assert scene.block_count() == 0
