"""WebSocket + HTTP bridge — syncs MCP scene with the web editor."""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import threading
import typing as typ

if typ.TYPE_CHECKING:
    import concurrent.futures

    from websockets.asyncio.server import ServerConnection

from .lifecycle_log import emit_lifecycle
from .model import SceneStore, VoxelScene

_LOG = logging.getLogger(__name__)

BRIDGE_HOST = "127.0.0.1"
BRIDGE_PORT = 8765
BRIDGE_HTTP_PORT = 8766
# 5173 remains available for the standalone `bun run dev` flow.
_DEFAULT_EDITOR_ORIGIN_PORT = 5173
_editor_origin_ports: set[int] = {_DEFAULT_EDITOR_ORIGIN_PORT}
_editor_origin_lock = threading.Lock()


def register_editor_origin(port: int) -> None:
    """Allow the editor served on loopback ``port`` to reach the bridge."""
    with _editor_origin_lock:
        _editor_origin_ports.add(int(port))


def unregister_editor_origin(port: int) -> None:
    """Revoke a supervised editor port while retaining the standalone default.

    Examples
    --------
    >>> register_editor_origin(45678)
    >>> unregister_editor_origin(45678)
    >>> "http://127.0.0.1:45678" in allowed_origins()
    False
    """
    if port != _DEFAULT_EDITOR_ORIGIN_PORT:
        with _editor_origin_lock:
            _editor_origin_ports.discard(port)


def allowed_origins() -> frozenset[str]:
    """Return the loopback origins currently allowed to use the bridge.

    Returns
    -------
    frozenset of str
        One ``127.0.0.1`` and one ``localhost`` origin per registered
        editor port.
    """
    with _editor_origin_lock:
        ports = tuple(_editor_origin_ports)
    return frozenset(
        origin
        for port in ports
        for origin in (f"http://127.0.0.1:{port}", f"http://localhost:{port}")
    )


store = SceneStore()
_clients: set[ServerConnection] = set()
_lock = threading.Lock()
_bridge_loop: asyncio.AbstractEventLoop | None = None
_current_ports: tuple[int, int] | None = None
_ready = threading.Event()


def current_ports() -> tuple[int, int] | None:
    """Return the bridge's bound (WebSocket, HTTP) ports, or None when down."""
    return _current_ports


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


_WS_POLICY_VIOLATION = 1008


def _ws_origin_allowed(websocket: ServerConnection) -> bool:
    """Check a connection's Origin header against the currently allowed origins."""
    request = getattr(websocket, "request", None)
    headers = getattr(request, "headers", None)
    origin = headers.get("Origin") if headers is not None else None
    return origin is None or origin in allowed_origins()


async def _ws_handler(
    websocket: ServerConnection,
) -> None:
    """Serve one editor websocket connection until the peer goes away."""
    if not _ws_origin_allowed(websocket):
        await websocket.close(_WS_POLICY_VIOLATION, "origin is not allowed")
        return
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


def _bound_port(server: typ.Any, requested: int) -> int:  # ruff: ignore[any-type]  # accepts asyncio and websockets servers
    """Read the port a server actually bound, falling back to the request."""
    sockets = getattr(server, "sockets", None)
    if sockets:
        return int(sockets[0].getsockname()[1])
    return requested


def _announce_stop() -> None:
    """Report the listener teardown that ``_run_servers`` performs in its finally.

    Called from that one site, so it cannot report a stop that did not happen
    or miss one that did. ``error_category`` is the class of whatever ended the
    listeners, which is ``CancelledError`` for the ordinary shutdown and
    ``none`` only when the task left the loop without raising; only the class
    is printed, because an exception's message may carry bound ports or
    editor-supplied data.
    """
    cause = sys.exception()
    category = type(cause).__name__ if cause is not None else "none"
    emit_lifecycle(
        "bridge", "bridge_state", bridge_state="down", error_category=category
    )


async def _run_servers(ws_port: int = 0, http_port: int = 0) -> None:
    """Run the websocket and HTTP servers until the task is cancelled.

    Both ports default to ``0`` so the operating system assigns free
    ephemeral ones; the bound ports are published through
    :func:`current_ports`. Origins are enforced per connection in the
    handlers, so an editor port registered after startup is honoured.
    """
    global _bridge_loop, _current_ports

    import websockets

    from voxel_forge import bridge_http

    ws_server = await websockets.serve(_ws_handler, BRIDGE_HOST, ws_port)
    http_server = await asyncio.start_server(
        bridge_http._http_handler, BRIDGE_HOST, http_port
    )
    bound_ws = _bound_port(ws_server, ws_port)
    bound_http = _bound_port(http_server, http_port)
    _bridge_loop = asyncio.get_running_loop()
    _current_ports = (bound_ws, bound_http)
    _ready.set()
    _startup_finished.set()
    print(
        f"VoxelForge bridge: ws://{BRIDGE_HOST}:{bound_ws}"
        f"  http://{BRIDGE_HOST}:{bound_http}",
        file=sys.stderr,
    )
    try:
        async with ws_server, http_server:
            await asyncio.Future()
    finally:
        _bridge_loop = None
        _current_ports = None
        _ready.clear()
        _announce_stop()


_bridge_thread: threading.Thread | None = None
_startup_finished = threading.Event()
_startup_error: BaseException | None = None
_STARTUP_TIMEOUT_SECONDS = 10.0


def start_bridge_background() -> tuple[int, int]:
    """Start the bridge once and return the ports it bound.

    Returns
    -------
    tuple[int, int]
        The WebSocket and HTTP ports that the operating system assigned.

    Raises
    ------
    RuntimeError
        If the bridge does not report readiness within its startup timeout.
    """
    global _bridge_thread, _startup_error
    with _lock:
        if not (_bridge_thread and _bridge_thread.is_alive()):
            _startup_error = None
            _startup_finished.clear()
            _ready.clear()

            async def capture_failure() -> None:
                """Transport server-task failures to the waiting caller."""
                global _startup_error
                try:
                    (result,) = await asyncio.gather(
                        _run_servers(), return_exceptions=True
                    )
                    if isinstance(result, BaseException):
                        _startup_error = result
                        _LOG.error("Bridge startup failed (%s)", type(result).__name__)
                finally:
                    _startup_finished.set()

            def run() -> None:
                """Run bridge listeners on their dedicated event loop."""
                asyncio.run(capture_failure())

            _bridge_thread = threading.Thread(target=run, daemon=True)
            _bridge_thread.start()
    if not _startup_finished.wait(_STARTUP_TIMEOUT_SECONDS):
        msg = "the bridge did not report readiness in time"
        raise RuntimeError(msg)
    if _startup_error is not None:
        msg = "the bridge failed to start"
        raise RuntimeError(msg) from _startup_error
    ports = _current_ports
    if ports is None:
        msg = "the bridge started but published no ports"
        raise RuntimeError(msg)
    return ports


def main() -> None:
    """Run the bridge on fixed ports by default, or on explicit port choices."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="voxel-forge-bridge",
        description="Run the VoxelForge editor bridge in the foreground.",
    )
    parser.add_argument(
        "--ws-port",
        type=int,
        default=BRIDGE_PORT,
        help="WebSocket port to bind (0 for an ephemeral one)",
    )
    parser.add_argument(
        "--http-port",
        type=int,
        default=BRIDGE_HTTP_PORT,
        help="HTTP port to bind (0 for an ephemeral one)",
    )
    args = parser.parse_args()
    asyncio.run(_run_servers(args.ws_port, args.http_port))


if __name__ == "__main__":
    main()
