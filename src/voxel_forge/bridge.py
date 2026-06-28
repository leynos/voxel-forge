"""WebSocket + HTTP bridge — syncs MCP scene with the web editor."""

from __future__ import annotations

import asyncio
import json
import threading
from typing import Any

from .model import SceneStore, VoxelScene

BRIDGE_HOST = "127.0.0.1"
BRIDGE_PORT = 8765
BRIDGE_HTTP_PORT = 8766

store = SceneStore()
_clients: set[Any] = set()
_lock = threading.Lock()


def _broadcast(payload: dict[str, Any]) -> None:
    """Schedule broadcast on the running event loop."""
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_async_broadcast(payload))
    except RuntimeError:
        pass


async def _async_broadcast(payload: dict[str, Any]) -> None:
    if not _clients:
        return
    msg = json.dumps(payload, ensure_ascii=False)
    dead: set[Any] = set()
    for ws in _clients:
        try:
            await ws.send(msg)
        except Exception:
            dead.add(ws)
    _clients.difference_update(dead)


def notify_scene_update(scene: VoxelScene) -> None:
    _broadcast({"type": "scene_update", "scene": scene.to_dict()})


async def _ws_handler(websocket) -> None:
    _clients.add(websocket)
    try:
        current = store._current
        if current and current in store._scenes:
            await websocket.send(
                json.dumps(
                    {"type": "scene_update", "scene": store._scenes[current].to_dict()},
                    ensure_ascii=False,
                )
            )
        async for raw in websocket:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if msg.get("type") == "get_scene":
                name = msg.get("name") or store._current
                if name and name in store._scenes:
                    await websocket.send(
                        json.dumps(
                            {"type": "scene_update", "scene": store._scenes[name].to_dict()},
                            ensure_ascii=False,
                        )
                    )
            elif msg.get("type") == "editor_place":
                scene = store.get(msg.get("scene_name"))
                scene.place(
                    int(msg["x"]),
                    int(msg["y"]),
                    int(msg["z"]),
                    str(msg.get("color", "1")),
                    msg.get("layer_index"),
                )
                await _async_broadcast({"type": "scene_update", "scene": scene.to_dict()})
    finally:
        _clients.discard(websocket)


async def _http_handler(reader, writer) -> None:
    header_bytes = await reader.readuntil(b"\r\n\r\n")
    header_text = header_bytes.decode("utf-8", errors="ignore")
    lines = header_text.split("\r\n")
    first = lines[0] if lines else ""
    method = first.split(" ")[0] if first else "GET"
    path = first.split(" ")[1] if " " in first else "/"
    content_length = 0
    for line in lines[1:]:
        if line.lower().startswith("content-length:"):
            content_length = int(line.split(":", 1)[1].strip())
            break

    payload_bytes = await reader.readexactly(content_length) if content_length > 0 else b""
    payload = payload_bytes.decode("utf-8")

    cors = b"Access-Control-Allow-Origin: *\r\nAccess-Control-Allow-Methods: GET, POST, OPTIONS\r\n"

    if method == "OPTIONS":
        writer.write(b"HTTP/1.1 204 No Content\r\n" + cors + b"\r\n")
        await writer.drain()
        writer.close()
        return

    body = b""
    status = b"HTTP/1.1 200 OK\r\n"

    if method == "POST" and path == "/scene":
        try:
            data = json.loads(payload)
            scene = VoxelScene.from_dict(data)
            store._scenes[scene.name] = scene
            store._current = scene.name
            await _async_broadcast({"type": "scene_update", "scene": scene.to_dict()})
            body = json.dumps({"ok": True, "name": scene.name, "blocks": scene.block_count()}).encode()
        except Exception as exc:
            status = b"HTTP/1.1 400 Bad Request\r\n"
            body = json.dumps({"error": str(exc)}).encode()
    elif method == "GET" and path == "/health":
        body = json.dumps({"ok": True, "editor_clients": len(_clients)}).encode()
    elif method == "GET" and path == "/scene":
        name = store._current
        if not name or name not in store._scenes:
            body = json.dumps({"error": "no active scene"}).encode()
        else:
            body = json.dumps(store._scenes[name].to_dict(), ensure_ascii=False).encode()
    else:
        body = json.dumps({"endpoints": ["GET /health", "GET /scene", "POST /scene"]}).encode()

    header = (
        status
        + cors
        + b"Content-Type: application/json\r\n"
        + f"Content-Length: {len(body)}\r\n\r\n".encode()
    )
    writer.write(header + body)
    await writer.drain()
    writer.close()


async def _run_servers() -> None:
    import websockets

    ws_server = await websockets.serve(_ws_handler, BRIDGE_HOST, BRIDGE_PORT)
    http_server = await asyncio.start_server(_http_handler, BRIDGE_HOST, BRIDGE_HTTP_PORT)
    print(f"VoxelForge bridge: ws://{BRIDGE_HOST}:{BRIDGE_PORT}  http://{BRIDGE_HOST}:{BRIDGE_HTTP_PORT}")
    async with ws_server, http_server:
        await asyncio.Future()


_bridge_thread: threading.Thread | None = None


def start_bridge_background() -> None:
    global _bridge_thread
    if _bridge_thread and _bridge_thread.is_alive():
        return

    def run() -> None:
        asyncio.run(_run_servers())

    _bridge_thread = threading.Thread(target=run, daemon=True)
    _bridge_thread.start()


def main() -> None:
    asyncio.run(_run_servers())


if __name__ == "__main__":
    main()
