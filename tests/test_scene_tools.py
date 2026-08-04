"""Contract tests for the scene-mutating MCP tools.

These tests call the tool functions directly against an isolated scene
store, covering the per-call voxel budget, the accepted block row
shapes, and the basic agent workflow.
"""

from __future__ import annotations

import json
import typing as typ

import pytest

from voxel_forge import server

if typ.TYPE_CHECKING:
    from pathlib import Path


def test_fill_box_rejects_more_than_limit_without_mutation(
    empty_server_store: None,
) -> None:
    """An oversized box fill must be refused before any voxel is placed."""
    server.store.create("bounded")

    with pytest.raises(ValueError, match="100,000"):
        server.voxelforge_fill_box(0, 100_000, 0, 0, 0, 0)

    assert server.store.get().block_count() == 0, "the scene must stay untouched"


def test_place_many_rejects_more_than_limit_without_mutation(
    empty_server_store: None,
) -> None:
    """An oversized batch place must be refused before any voxel lands."""
    server.store.create("bounded")
    blocks = [[index, 0, 0, "1"] for index in range(100_001)]

    with pytest.raises(ValueError, match="100,000"):
        server.voxelforge_place_many(json.dumps(blocks))

    assert server.store.get().block_count() == 0, "the scene must stay untouched"


def test_place_many_accepts_object_rows(empty_server_store: None) -> None:
    """Object-shaped rows must place voxels exactly like array rows."""
    server.store.create("shapes")
    blocks = [
        [0, 0, 0, "#3CB043"],
        {"x": 1, "y": 0, "z": 0, "color": "#3CB043"},
        {"x": 2, "y": 0, "z": 0, "colour": "#3CB043"},
    ]

    result = server.voxelforge_place_many(json.dumps(blocks))

    assert "Placed 3 voxels" in result, "all three row shapes must be accepted"
    assert server.store.get().block_count() == 3, "each row must land as a voxel"


@pytest.mark.parametrize(
    "row",
    [
        {"x": 1, "y": 0, "z": 0},
        {"x": 1, "y": 0, "color": "#3CB043"},
        [1, 0, "#3CB043"],
        [1, 0, 0, "#3CB043", "surplus"],
        {"x": 1, "y": 0, "z": None, "color": "#3CB043"},
        "1,0,0,#3CB043",
    ],
)
def test_place_many_rejects_malformed_rows(
    empty_server_store: None, row: object
) -> None:
    """Rows matching neither documented shape must be refused clearly."""
    server.store.create("shapes")

    with pytest.raises(ValueError, match="malformed block row"):
        server.voxelforge_place_many(json.dumps([row]))

    assert server.store.get().block_count() == 0, "the scene must stay untouched"


def test_basic_agent_scene_workflow(
    empty_server_store: None, scene_directory: Path
) -> None:
    """The core agent tools must create, edit, save, and reload a scene."""
    assert "basic" in server.voxelforge_create_scene("basic"), "the scene must exist"
    assert "Placed" in server.voxelforge_place_block(0, 0, 0, "2"), "placing must work"
    assert "Filled" in server.voxelforge_fill_box(1, 2, 0, 0, 0, 0, "3"), (
        "filling must be confirmed"
    )
    assert server.store.get().block_count() == 3, "three voxels must be present"
    assert "Saved" in server.voxelforge_save(), "the save must be confirmed"

    server.store = server.SceneStore()
    assert "Loaded" in server.voxelforge_load("basic"), "the load must be confirmed"
    assert server.store.get().block_count() == 3, "the saved voxels must return"
