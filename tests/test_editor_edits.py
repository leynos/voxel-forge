"""Layer-aware WebSocket editing and post-mutation publication contracts."""

from __future__ import annotations

import asyncio
import dataclasses
import json
import typing as typ

import pytest
from readiness_helpers import EditorSocket

from voxel_forge import bridge
from voxel_forge.model import SceneStore, VoxelScene


@dataclasses.dataclass(frozen=True, slots=True)
class _EditorCase:
    """Edit command, requested layer, and expected total after one mutation."""

    command: str
    layer_index: int
    expected_count: int


@pytest.mark.parametrize("coordinates", [(1, 2, 3), ("1", "2", "3")])
@pytest.mark.parametrize(
    "case",
    [
        _EditorCase("editor_place", 0, 1),
        _EditorCase("editor_remove", 0, 0),
        _EditorCase("editor_remove", 1, 0),
    ],
    ids=["place", "remove-clicked", "remove-stale-layer"],
)
def test_editor_edits_update_server_scene(
    editor_bridge: tuple[SceneStore, asyncio.Queue[dict[str, typ.Any]]],
    coordinates: tuple[int | str, int | str, int | str],
    case: _EditorCase,
) -> None:
    """Route both edit variants, preserving clicked-layer and stale-layer removal."""
    store, broadcasts = editor_bridge
    scene = store.create("editor")
    scene.add_layer("upper")
    scene.active_layer = 1
    scene.place(1, 2, 3, "1", layer_index=0)
    x, y, z = coordinates
    message = {
        "type": case.command,
        "scene_name": "editor",
        "layer_index": case.layer_index,
        "x": x,
        "y": y,
        "z": z,
        "color": "2",
    }
    asyncio.run(bridge._ws_handler(EditorSocket([json.dumps(message)])))
    snapshot = VoxelScene.from_dict(broadcasts.get_nowait()["scene"])
    assert scene.block_count() == case.expected_count, (
        "the edit must change the target voxel"
    )
    assert scene.layers[1].blocks == {}, (
        "a lower-layer edit must leave the active layer untouched"
    )
    assert snapshot.to_dict() == scene.to_dict(), (
        "publication must include the complete edit"
    )
    if case.command == "editor_place":
        assert scene.layers[0].blocks[1, 2, 3] == "2", (
            "placement must retain the chosen colour"
        )
