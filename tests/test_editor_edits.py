"""WebSocket edit routing and post-mutation broadcast contracts."""

from __future__ import annotations

import asyncio
import json
import typing as typ

import pytest

from voxel_forge import bridge
from voxel_forge.model import SceneStore, VoxelScene


@pytest.mark.parametrize(
    ("command", "expected_count"), [("editor_remove", 0), ("editor_place", 1)]
)
def test_editor_edits_update_server_scene(
    monkeypatch: pytest.MonkeyPatch, command: str, expected_count: int
) -> None:
    """Both editor variants must mutate the target scene and publish its snapshot."""
    store = SceneStore()
    scene = store.create("editor")
    scene.place(1, 2, 3, "1")
    monkeypatch.setattr(bridge, "store", store)
    broadcasts: asyncio.Queue[VoxelScene] = asyncio.Queue()

    async def capture(
        payload: dict[str, typ.Any],
    ) -> None:
        await broadcasts.put(VoxelScene.from_dict(payload["scene"]))

    monkeypatch.setattr(bridge, "_async_broadcast", capture)

    class WebSocket:
        def __init__(self) -> None:
            self.messages = iter([
                json.dumps({
                    "type": command,
                    "scene_name": "editor",
                    "layer_index": 0,
                    "x": "1",
                    "y": "2",
                    "z": "3",
                    "color": "2",
                })
            ])

        def __aiter__(self) -> typ.Self:
            return self

        async def __anext__(self) -> str:
            try:
                return next(self.messages)
            except StopIteration as exc:
                raise StopAsyncIteration from exc

        async def send(self, _message: str) -> None:
            return None

    asyncio.run(bridge._ws_handler(WebSocket()))

    assert scene.block_count() == expected_count, (
        "the edit must change the target voxel"
    )
    snapshot = broadcasts.get_nowait()
    assert snapshot.name == "editor", "the update must name the target scene"
    assert snapshot.block_count() == expected_count, "the update must include the edit"
    if command == "editor_place":
        assert scene.layer.blocks[1, 2, 3] == "2", (
            "placement must keep the chosen colour"
        )
