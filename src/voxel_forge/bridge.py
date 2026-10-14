"""WebSocket + HTTP bridge — syncs MCP scene with the web editor."""

from __future__ import annotations

import asyncio
import json
import sys
import threading
import typing as typ

if typ.TYPE_CHECKING:
    import concurrent.futures

    from websockets.asyncio.server import ServerConnection

from .model import SceneStore, VoxelScene

BRIDGE_HOST = "127.0.0.1"
BRIDGE_PORT = 8765
BRIDGE_HTTP_PORT = 8766
ALLOWED_EDITOR_ORIGINS = frozenset({"http://127.0.0.1:5173", "http://localhost:5173"})
MAX_HTTP_BODY_BYTES = 10_000_000

_STATUS_OK = b"HTTP/1.1 200 OK\r\n"
_STATUS_NO_CONTENT = b"HTTP/1.1 204 No Content\r\n"
_STATUS_BAD_REQUEST = b"HTTP/1.1 400 Bad Request\r\n"
_STATUS_FORBIDDEN = b"HTTP/1.1 403 Forbidden\r\n"
_STATUS_TOO_LARGE = b"HTTP/1.1 413 Content Too Large\r\n"
_JSON_CONTENT_TYPE = b"Content-Type: application/json\r\n"
_CORS_METHODS = b"Access-Control-Allow-Methods: GET, POST, OPTIONS\r\n"

store = SceneStore()
_clients: set[ServerConnection] = set()
_lock = threading.Lock()
_bridge_loop: asyncio.AbstractEventLoop | None = None


def use_store(shared: SceneStore) -> None:
    """Adopt the MCP server's registry as this bridge's single source of scenes.

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


def _report_broadcast_failure(future: concurrent.futures.Future[None]) -> None:
    """Report an unexpected broadcast failure on stderr, keeping stdout protocol-.

    clean.
    """
    if future.cancelled():
        return
    error = future.exception()
    if error is not None:
        print(
            f"VoxelForge bridge: broadcast failed: {type(error).__name__}: {error}",
            file=sys.stderr,
        )


def _layer_index(message: dict[str, typ.Any], scene: VoxelScene) -> int:
    """Resolve an editor request's layer index, defaulting to the scene's active.

    layer.
    """
    raw = message.get("layer_index")
    return scene.active_layer if raw is None else int(raw)


def _block_coordinate(message: dict[str, typ.Any]) -> tuple[int, int, int]:
    """Return the grid coordinate an editor request targets."""
    return int(message["x"]), int(message["y"]), int(message["z"])


def _broadcast(payload: dict[str, typ.Any]) -> None:
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


async def _async_broadcast(payload: dict[str, typ.Any]) -> None:
    """Send one payload to every connected editor, dropping dead peers."""
    if not _clients:
        return
    msg = json.dumps(payload, ensure_ascii=False)
    dead: set[ServerConnection] = set()
    for ws in _clients:
        try:
            await ws.send(msg)
        except Exception:  # ruff: ignore[blind-except]  # a failed peer must not stop the loop
            dead.add(ws)
    _clients.difference_update(dead)


def notify_scene_update(scene: VoxelScene) -> None:
    """Announce a scene's current state to every connected editor.

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


async def _send_scene(websocket: ServerConnection, name: str | None) -> None:
    """Send a consistent named or current scene snapshot when it exists."""
    with store.lock:
        scene = store.get_or_none(name)
        snapshot = scene.to_dict() if scene is not None else None
    if snapshot is not None:
        await websocket.send(
            json.dumps({"type": "scene_update", "scene": snapshot}, ensure_ascii=False)
        )


async def _apply_editor_edit(msg: dict[str, typ.Any]) -> None:
    """Apply one layer-aware edit atomically and broadcast its snapshot."""
    with store.lock:
        scene = store.get_or_none(msg.get("scene_name"))
        if scene is None:
            return
        coordinates = _block_coordinate(msg)
        layer_index = _layer_index(msg, scene)
        match msg["type"]:
            case "editor_place":
                scene.place(*coordinates, str(msg.get("color", "1")), layer_index)
            case "editor_remove":
                if not scene.remove(*coordinates, layer_index):
                    scene.remove_from_any_layer(*coordinates)
            case _:
                msg_error = f"unsupported editor edit: {msg['type']}"
                raise ValueError(msg_error)
        snapshot = scene.to_dict()
    await _async_broadcast({"type": "scene_update", "scene": snapshot})


async def _ws_handler(
    websocket: ServerConnection,
) -> None:
    """Serve one editor websocket connection until the peer goes away."""
    _clients.add(websocket)
    try:
        await _send_scene(websocket, None)
        async for raw in websocket:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            match msg.get("type"):
                case "get_scene":
                    await _send_scene(websocket, msg.get("name"))
                case "editor_place" | "editor_remove":
                    try:
                        await _apply_editor_edit(msg)
                    except (KeyError, TypeError, ValueError) as exc:
                        print(
                            "VoxelForge bridge: invalid editor edit: "
                            f"{type(exc).__name__}",
                            file=sys.stderr,
                        )
    finally:
        _clients.discard(websocket)


class _HttpRequest(typ.NamedTuple):
    """The parts of an HTTP request head that the bridge acts upon."""

    method: str
    path: str
    content_length: int
    origin: str | None


def _parse_request_head(header_text: str) -> _HttpRequest:
    """Pull the method, path, body length and origin out of a request head."""
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
    return _HttpRequest(method, path, content_length, origin)


def _cors_headers(origin: str | None) -> bytes:
    """Return the CORS headers granted to ``origin``."""
    headers = _CORS_METHODS
    if origin in ALLOWED_EDITOR_ORIGINS:
        headers += f"Access-Control-Allow-Origin: {origin}\r\nVary: Origin\r\n".encode()
    return headers


async def _close_connection(writer: asyncio.StreamWriter) -> None:
    """Flush and close one client connection."""
    await writer.drain()
    writer.close()
    await writer.wait_closed()


async def _write_response(
    writer: asyncio.StreamWriter, status: bytes, headers: bytes, body: bytes
) -> None:
    """Write one JSON response and close the connection."""
    writer.write(
        status
        + headers
        + _JSON_CONTENT_TYPE
        + f"Content-Length: {len(body)}\r\n\r\n".encode()
        + body
    )
    await _close_connection(writer)


async def _handle_scene_post(payload: str) -> tuple[bytes, bytes]:
    """Replace the active scene from a JSON body and broadcast the result."""
    try:
        scene = VoxelScene.from_dict(json.loads(payload))
        with store.lock:
            store.register(scene)
            snapshot = scene.to_dict()
            blocks = scene.block_count()
        await _async_broadcast({"type": "scene_update", "scene": snapshot})
        body = json.dumps({
            "ok": True,
            "name": scene.name,
            "blocks": blocks,
        }).encode()
    except Exception as exc:  # ruff: ignore[blind-except]  # any bad payload answers 400
        return _STATUS_BAD_REQUEST, json.dumps({"error": str(exc)}).encode()
    return _STATUS_OK, body


def _current_scene_body() -> bytes:
    """Serialize the current scene under the shared registry lock."""
    with store.lock:
        scene = store.get_or_none()
        snapshot = scene.to_dict() if scene is not None else None
    if snapshot is None:
        return json.dumps({"error": "no active scene"}).encode()
    return json.dumps(snapshot, ensure_ascii=False).encode()


async def _route_request(request: _HttpRequest, payload: str) -> tuple[bytes, bytes]:
    """Dispatch one request, returning its status line and response body."""
    match (request.method, request.path):
        case ("POST", "/scene"):
            return await _handle_scene_post(payload)
        case ("GET", "/health"):
            health = {"ok": True, "editor_clients": len(_clients)}
            return _STATUS_OK, json.dumps(health).encode()
        case ("GET", "/scene"):
            return _STATUS_OK, _current_scene_body()
        case _:
            endpoints = {"endpoints": ["GET /health", "GET /scene", "POST /scene"]}
            return _STATUS_OK, json.dumps(endpoints).encode()


async def _http_handler(
    reader: asyncio.StreamReader, writer: asyncio.StreamWriter
) -> None:
    """Serve the bridge's small HTTP API on one connection."""
    header_bytes = await reader.readuntil(b"\r\n\r\n")
    request = _parse_request_head(header_bytes.decode("utf-8", errors="ignore"))
    cors = _cors_headers(request.origin)

    if request.origin is not None and request.origin not in ALLOWED_EDITOR_ORIGINS:
        body = json.dumps({"error": "origin is not allowed"}).encode()
        await _write_response(writer, _STATUS_FORBIDDEN, b"", body)
        return

    if request.content_length < 0 or request.content_length > MAX_HTTP_BODY_BYTES:
        body = json.dumps({"error": "request body is too large"}).encode()
        await _write_response(writer, _STATUS_TOO_LARGE, cors, body)
        return

    payload_bytes = (
        await reader.readexactly(request.content_length)
        if request.content_length
        else b""
    )
    payload = payload_bytes.decode("utf-8")

    if request.method == "OPTIONS":
        writer.write(_STATUS_NO_CONTENT + cors + b"\r\n")
        await _close_connection(writer)
        return

    status, body = await _route_request(request, payload)
    await _write_response(writer, status, cors, body)


async def _run_servers() -> None:
    """Run the websocket and HTTP servers until the task is cancelled."""
    global _bridge_loop

    import websockets

    ws_server = await websockets.serve(
        _ws_handler,
        BRIDGE_HOST,
        BRIDGE_PORT,
        origins=[None, *sorted(ALLOWED_EDITOR_ORIGINS)],
    )
    http_server = await asyncio.start_server(
        _http_handler, BRIDGE_HOST, BRIDGE_HTTP_PORT
    )
    _bridge_loop = asyncio.get_running_loop()
    print(
        f"VoxelForge bridge: ws://{BRIDGE_HOST}:{BRIDGE_PORT}"
        f"  http://{BRIDGE_HOST}:{BRIDGE_HTTP_PORT}",
        file=sys.stderr,
    )
    try:
        async with ws_server, http_server:
            await asyncio.Future()
    finally:
        _bridge_loop = None


_bridge_thread: threading.Thread | None = None


def start_bridge_background() -> None:
    """Start the bridge on a daemon thread unless it is already running."""
    global _bridge_thread
    with _lock:
        if _bridge_thread and _bridge_thread.is_alive():
            return

        _bridge_thread = threading.Thread(target=main, daemon=True)
        _bridge_thread.start()


def main() -> None:
    """Run the bridge in the foreground."""
    asyncio.run(_run_servers())


if __name__ == "__main__":
    main()
