from __future__ import annotations

import asyncio
from typing import Any

import pytest

from voxel_forge import bridge
from voxel_forge.model import SceneStore


def test_broadcast_submits_to_bridge_event_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    submitted: list[tuple[Any, Any]] = []
    bridge_loop = object()
    monkeypatch.setattr(bridge, "_bridge_loop", bridge_loop, raising=False)

    def capture(coroutine: Any, loop: Any) -> None:
        submitted.append((coroutine, loop))
        coroutine.close()

    monkeypatch.setattr(asyncio, "run_coroutine_threadsafe", capture)

    bridge._broadcast({"type": "scene_update"})

    assert len(submitted) == 1
    assert submitted[0][1] is bridge_loop


def test_editor_remove_updates_server_scene(monkeypatch: pytest.MonkeyPatch) -> None:
    store = SceneStore()
    scene = store.create("editor")
    scene.place(1, 2, 3, "1")
    monkeypatch.setattr(bridge, "store", store)
    broadcasts: list[dict[str, Any]] = []

    async def capture(payload: dict[str, Any]) -> None:
        broadcasts.append(payload)

    monkeypatch.setattr(bridge, "_async_broadcast", capture)

    class WebSocket:
        def __init__(self) -> None:
            self.messages = iter(['{"type":"editor_remove","scene_name":"editor","layer_index":0,"x":1,"y":2,"z":3}'])

        def __aiter__(self):
            return self

        async def __anext__(self) -> str:
            try:
                return next(self.messages)
            except StopIteration as exc:
                raise StopAsyncIteration from exc

        async def send(self, _message: str) -> None:
            return None

    asyncio.run(bridge._ws_handler(WebSocket()))

    assert scene.block_count() == 0
    assert broadcasts[-1]["scene"]["name"] == "editor"
