from __future__ import annotations

import json

import pytest

from voxel_forge import server


@pytest.fixture(autouse=True)
def empty_store(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(server, "store", server.SceneStore())
    monkeypatch.setattr(server, "_sync_bridge", lambda _scene: None)


def test_fill_box_rejects_more_than_limit_without_mutation() -> None:
    server.store.create("bounded")

    with pytest.raises(ValueError, match="100,000"):
        server.voxelforge_fill_box(0, 100_000, 0, 0, 0, 0)

    assert server.store.get().block_count() == 0


def test_place_many_rejects_more_than_limit_without_mutation() -> None:
    server.store.create("bounded")
    blocks = [[index, 0, 0, "1"] for index in range(100_001)]

    with pytest.raises(ValueError, match="100,000"):
        server.voxelforge_place_many(json.dumps(blocks))

    assert server.store.get().block_count() == 0


def test_basic_agent_scene_workflow(scene_directory) -> None:
    assert "basic" in server.voxelforge_create_scene("basic")
    assert "วาง" in server.voxelforge_place_block(0, 0, 0, "2")
    assert "เติม" in server.voxelforge_fill_box(1, 2, 0, 0, 0, 0, "3")
    assert server.store.get().block_count() == 3
    assert "บันทึก" in server.voxelforge_save()

    server.store = server.SceneStore()
    assert "โหลด" in server.voxelforge_load("basic")
    assert server.store.get().block_count() == 3
