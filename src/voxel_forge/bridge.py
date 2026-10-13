"""WebSocket + HTTP bridge — syncs MCP scene with the web editor."""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import sys
import threading
from typing import Any

from .model import SceneStore, VoxelScene

BRIDGE_HOST = "127.0.0.1"
BRIDGE_PORT = 8765
BRIDGE_HTTP_PORT = 8766
ALLOWED_EDITOR_ORIGINS = frozenset({"http://127.0.0.1:5173", "http://localhost:5173"})
MAX_HTTP_BODY_BYTES = 10_000_000

store = SceneStore()
_clients: set[Any] = set()
_lock = threading.Lock()
_bridge_loop: asyncio.AbstractEventLoop | None = None


def use_store(shared: SceneStore) -> None:
    """
    Adopt the MCP server's registry as this bridge's single source of scenes.

    The server passes its own :class:`~voxel_forge.model.SceneStore`, so the
    MCP tool surface and the editor bridge read and mutate the same scenes
    through the same store — and therefore the same :attr:`SceneStore.lock`.
    Rebinding the whole store keeps one owner of scene state instead of two
    registries whose dicts merely happen to point at the same objects.

    Parameters
    ----------
    shared : SceneStore
        The registry the bridge should serve and mutate.
    """
    global store
    store = shared


def _broadcast(payload: dict[str, Any]) -> None:
    """Submit a broadcast to the bridge event loop from any thread."""
    loop = _bridge_loop
    if loop is None:
        return
    coroutine = _async_broadcast(payload)
    try:
        future = asyncio.run_coroutine_threadsafe(coroutine, loop)
    except RuntimeError:
        coroutine.close()
        return
    future.add_done_callback(_report_broadcast_failure)


def _report_broadcast_failure(future: concurrent.futures.Future[None]) -> None:
    """Report an unexpected broadcast failure on stderr, keeping stdout protocol-clean."""
    if future.cancelled():
        return
    error = future.exception()
    if error is not None:
        print(f"VoxelForge bridge: broadcast failed: {type(error).__name__}: {error}", file=sys.stderr)


def _layer_index(message: dict[str, Any], scene: VoxelScene) -> int:
    """Resolve an editor request's layer index, defaulting to the scene's active layer."""
    raw = message.get("layer_index")
    return scene.active_layer if raw is None else int(raw)


def _block_coordinate(message: dict[str, Any]) -> tuple[int, int, int]:
    """Return the grid coordinate an editor request targets."""
    return int(message["x"]), int(message["y"]), int(message["z"])


async def _async_broadcast(payload: dict[str, Any]) -> None:
    """Send one payload to every connected editor, dropping clients that fail."""
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
    """
    Announce a scene's current state to every connected editor.

    The snapshot is taken under the store lock, so an editor never receives a
    payload serialised from a scene that an MCP tool is midway through
    mutating. The caller is expected to hold the lock already — the MCP tools
    do — and the re-entrant lock makes the nested acquisition safe.

    Parameters
    ----------
    scene : VoxelScene
        Scene whose current state should be broadcast.
    """
    with store.lock:
        payload = {"type": "scene_update", "scene": scene.to_dict()}
    _broadcast(payload)


async def _ws_handler(websocket) -> None:
    """Serve one editor connection: push the current scene, then apply its edits."""
    _clients.add(websocket)
    try:
        with store.lock:
            current = store.get_or_none()
            initial = (
                None
                if current is None
                else json.dumps(
                    {"type": "scene_update", "scene": current.to_dict()},
                    ensure_ascii=False,
                )
            )
        if initial is not None:
            await websocket.send(initial)
        async for raw in websocket:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if msg.get("type") == "get_scene":
                with store.lock:
                    scene = store.get_or_none(msg.get("name"))
                    snapshot = scene.to_dict() if scene is not None else None
                if snapshot is not None:
                    await websocket.send(json.dumps({"type": "scene_update", "scene": snapshot}, ensure_ascii=False))
            elif msg.get("type") == "editor_place":
                with store.lock:
                    scene = store.get_or_none(msg.get("scene_name"))
                    if scene is None:
                        continue
                    x, y, z = _block_coordinate(msg)
                    scene.place(x, y, z, str(msg.get("color", "1")), _layer_index(msg, scene))
                    snapshot = scene.to_dict()
                await _async_broadcast({"type": "scene_update", "scene": snapshot})
            elif msg.get("type") == "editor_remove":
                with store.lock:
                    scene = store.get_or_none(msg.get("scene_name"))
                    if scene is None:
                        continue
                    x, y, z = _block_coordinate(msg)
                    layer_index = _layer_index(msg, scene)
                    # The editor picks the topmost rendered voxel, which may
                    # belong to a non-active layer. Fall back to any layer
                    # holding that coordinate so a removal is never silently
                    # dropped.
                    if not scene.remove(x, y, z, layer_index):
                        scene.remove_from_any_layer(x, y, z)
                    snapshot = scene.to_dict()
                await _async_broadcast({"type": "scene_update", "scene": snapshot})
    finally:
        _clients.discard(websocket)


async def _http_handler(reader, writer) -> None:
    """Serve one HTTP request, rejecting non-local origins and oversized bodies."""
    header_bytes = await reader.readuntil(b"\r\n\r\n")
    header_text = header_bytes.decode("utf-8", errors="ignore")
    lines = header_text.split("\r\n")
    first = lines[0] if lines else ""
    method = first.split(" ")[0] if first else "GET"
    path = first.split(" ")[1] if " " in first else "/"
    content_length = 0
    origin: str | None = None
    for line in lines[1:]:
        if line.lower().startswith("content-length:"):
            content_length = int(line.split(":", 1)[1].strip())
        elif line.lower().startswith("origin:"):
            origin = line.split(":", 1)[1].strip()

    allowed_origin = origin is None or origin in ALLOWED_EDITOR_ORIGINS
    cors = b"Access-Control-Allow-Methods: GET, POST, OPTIONS\r\n"
    if origin in ALLOWED_EDITOR_ORIGINS:
        cors += f"Access-Control-Allow-Origin: {origin}\r\nVary: Origin\r\n".encode()

    if not allowed_origin:
        body = json.dumps({"error": "origin is not allowed"}).encode()
        writer.write(
            b"HTTP/1.1 403 Forbidden\r\n"
            + b"Content-Type: application/json\r\n"
            + f"Content-Length: {len(body)}\r\n\r\n".encode()
            + body
        )
        await writer.drain()
        writer.close()
        await writer.wait_closed()
        return

    if content_length < 0 or content_length > MAX_HTTP_BODY_BYTES:
        body = json.dumps({"error": "request body is too large"}).encode()
        writer.write(
            b"HTTP/1.1 413 Content Too Large\r\n"
            + cors
            + b"Content-Type: application/json\r\n"
            + f"Content-Length: {len(body)}\r\n\r\n".encode()
            + body
        )
        await writer.drain()
        writer.close()
        await writer.wait_closed()
        return

    payload_bytes = await reader.readexactly(content_length) if content_length else b""
    payload = payload_bytes.decode("utf-8")

    if method == "OPTIONS":
        writer.write(b"HTTP/1.1 204 No Content\r\n" + cors + b"\r\n")
        await writer.drain()
        writer.close()
        await writer.wait_closed()
        return

    body = b""
    status = b"HTTP/1.1 200 OK\r\n"

    if method == "POST" and path == "/scene":
        try:
            data = json.loads(payload)
            scene = VoxelScene.from_dict(data)
            with store.lock:
                store.register(scene)
                snapshot = scene.to_dict()
                blocks = scene.block_count()
            await _async_broadcast({"type": "scene_update", "scene": snapshot})
            body = json.dumps({"ok": True, "name": scene.name, "blocks": blocks}).encode()
        except Exception as exc:
            status = b"HTTP/1.1 400 Bad Request\r\n"
            body = json.dumps({"error": str(exc)}).encode()
    elif method == "GET" and path == "/health":
        body = json.dumps({"ok": True, "editor_clients": len(_clients)}).encode()
    elif method == "GET" and path == "/scene":
        with store.lock:
            scene = store.get_or_none()
            snapshot = scene.to_dict() if scene is not None else None
        if snapshot is None:
            body = json.dumps({"error": "no active scene"}).encode()
        else:
            body = json.dumps(snapshot, ensure_ascii=False).encode()
    else:
        body = json.dumps({"endpoints": ["GET /health", "GET /scene", "POST /scene"]}).encode()

    header = status + cors + b"Content-Type: application/json\r\n" + f"Content-Length: {len(body)}\r\n\r\n".encode()
    writer.write(header + body)
    await writer.drain()
    writer.close()
    await writer.wait_closed()


async def _run_servers() -> None:
    """Serve the editor WebSocket and HTTP bridge until cancelled."""
    global _bridge_loop

    import websockets

    ws_server = await websockets.serve(
        _ws_handler,
        BRIDGE_HOST,
        BRIDGE_PORT,
        origins=[None, *sorted(ALLOWED_EDITOR_ORIGINS)],
    )
    http_server = await asyncio.start_server(_http_handler, BRIDGE_HOST, BRIDGE_HTTP_PORT)
    _bridge_loop = asyncio.get_running_loop()
    print(
        f"VoxelForge bridge: ws://{BRIDGE_HOST}:{BRIDGE_PORT}  http://{BRIDGE_HOST}:{BRIDGE_HTTP_PORT}",
        file=sys.stderr,
    )
    try:
        async with ws_server, http_server:
            await asyncio.Future()
    finally:
        _bridge_loop = None


_bridge_thread: threading.Thread | None = None


def start_bridge_background() -> None:
    global _bridge_thread
    with _lock:
        if _bridge_thread and _bridge_thread.is_alive():
            return

        _bridge_thread = threading.Thread(target=main, daemon=True)
        _bridge_thread.start()


def main() -> None:
    asyncio.run(_run_servers())


if __name__ == "__main__":
    main()
