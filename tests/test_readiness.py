from __future__ import annotations

import asyncio
import contextlib
import json
import struct
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from voxel_forge import bridge, server
from voxel_forge.model import SceneStore, VoxelScene
from voxel_forge.vox_io import export_vox, import_vox


def exchange_http(request: bytes) -> bytes:
    async def exchange() -> bytes:
        http_server = await asyncio.start_server(bridge._http_handler, "127.0.0.1", 0)
        port = http_server.sockets[0].getsockname()[1]
        async with http_server:
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.write(request)
            await writer.drain()
            response = await reader.read()
            writer.close()
            await writer.wait_closed()
        return response

    return asyncio.run(exchange())


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


def test_broadcast_submits_to_bridge_event_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    submitted: list[tuple[Any, Any]] = []
    bridge_loop = object()
    monkeypatch.setattr(bridge, "_bridge_loop", bridge_loop)

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


def test_http_bridge_rejects_non_local_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    store = SceneStore()
    monkeypatch.setattr(bridge, "store", store)
    payload = b'{"name":"hostile"}'
    request = (
        b"POST /scene HTTP/1.1\r\n"
        b"Host: 127.0.0.1:8766\r\n"
        b"Origin: https://example.invalid\r\n" + f"Content-Length: {len(payload)}\r\n\r\n".encode() + payload
    )

    response = exchange_http(request)

    assert response.startswith(b"HTTP/1.1 403 Forbidden")
    assert store.list_active() == []


def test_bridge_diagnostic_uses_stderr(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    class DummyServer:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

    async def make_server(*_args, **_kwargs):
        return DummyServer()

    monkeypatch.setitem(sys.modules, "websockets", SimpleNamespace(serve=make_server))
    monkeypatch.setattr(asyncio, "start_server", make_server)

    async def run_until_started() -> None:
        task = asyncio.create_task(bridge._run_servers())
        await asyncio.sleep(0)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    asyncio.run(run_until_started())
    captured = capsys.readouterr()

    assert captured.out == ""
    assert "VoxelForge bridge:" in captured.err


def test_windows_mcp_launcher_uses_installed_entrypoint() -> None:
    launcher = Path("run-mcp.bat").read_text(encoding="utf-8")

    assert "uv run voxel-forge-mcp" in launcher
    assert "python src/voxel_forge/server.py" not in launcher


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


@pytest.fixture
def empty_server_store(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(server, "store", server.SceneStore())
    monkeypatch.setattr(server, "_sync_bridge", lambda _scene: None)


def test_fill_box_rejects_more_than_limit_without_mutation(empty_server_store) -> None:
    server.store.create("bounded")

    with pytest.raises(ValueError, match="100,000"):
        server.voxelforge_fill_box(0, 100_000, 0, 0, 0, 0)

    assert server.store.get().block_count() == 0


def test_place_many_rejects_more_than_limit_without_mutation(empty_server_store) -> None:
    server.store.create("bounded")
    blocks = [[index, 0, 0, "1"] for index in range(100_001)]

    with pytest.raises(ValueError, match="100,000"):
        server.voxelforge_place_many(json.dumps(blocks))

    assert server.store.get().block_count() == 0


def test_basic_agent_scene_workflow(empty_server_store, scene_directory) -> None:
    assert "basic" in server.voxelforge_create_scene("basic")
    assert "วาง" in server.voxelforge_place_block(0, 0, 0, "2")
    assert "เติม" in server.voxelforge_fill_box(1, 2, 0, 0, 0, 0, "3")
    assert server.store.get().block_count() == 3
    assert "บันทึก" in server.voxelforge_save()

    server.store = server.SceneStore()
    assert "โหลด" in server.voxelforge_load("basic")
    assert server.store.get().block_count() == 3


def test_export_contains_required_chunks_in_order(tmp_path: Path) -> None:
    scene = VoxelScene("chunks")
    scene.place(2, 3, 4, "2")
    path = export_vox(scene, tmp_path / "chunks.vox")
    data = path.read_bytes()

    assert data.index(b"SIZE") < data.index(b"XYZI") < data.index(b"RGBA")
    chunks = child_chunks(data)
    assert struct.unpack("<III", chunks[b"SIZE"]) == (1, 1, 1)
    assert struct.unpack_from("<I", chunks[b"XYZI"])[0] == 1


@pytest.mark.parametrize("hex_colour", ["#123456", "#000000"])
def test_export_preserves_hex_colour_through_round_trip(tmp_path: Path, hex_colour: str) -> None:
    scene = VoxelScene("colour")
    scene.place(0, 0, 0, hex_colour)

    loaded = import_vox(export_vox(scene, tmp_path / "colour.vox"))
    colour_key = loaded.layer.blocks[(0, 0, 0)]

    assert loaded.resolve_color(colour_key) == scene.resolve_color(hex_colour)


def test_export_rejects_unrepresentable_dimension(tmp_path: Path) -> None:
    scene = VoxelScene("wide")
    scene.place(0, 0, 0, "1")
    scene.place(256, 0, 0, "1")

    with pytest.raises(ValueError, match="256"):
        export_vox(scene, tmp_path / "wide.vox")
