"""WebSocket + HTTP bridge — syncs MCP scene with the web editor."""

from __future__ import annotations

import asyncio
import json
import sys
import threading
import typing as typ

from .model import SceneStore, VoxelScene

BRIDGE_HOST = "127.0.0.1"
BRIDGE_PORT = 8765
BRIDGE_HTTP_PORT = 8766
# 5173 stays registered for the standalone `bun run dev` flow; supervised
# editors register their discovered ports at launch time.
_DEFAULT_EDITOR_ORIGIN_PORT = 5173
_editor_origin_ports: set[int] = {_DEFAULT_EDITOR_ORIGIN_PORT}


def register_editor_origin(port: int) -> None:
    """Allow the editor served on loopback ``port`` to reach the bridge."""
    _editor_origin_ports.add(int(port))


def allowed_origins() -> frozenset[str]:
    """Return the loopback origins currently allowed to use the bridge.

    Returns
    -------
    frozenset of str
        One ``127.0.0.1`` and one ``localhost`` origin per registered
        editor port.
    """
    return frozenset(
        origin
        for port in _editor_origin_ports
        for origin in (f"http://127.0.0.1:{port}", f"http://localhost:{port}")
    )


store = SceneStore()
_clients: set[typ.Any] = set()
_lock = threading.Lock()
_bridge_loop: asyncio.AbstractEventLoop | None = None
_current_ports: tuple[int, int] | None = None
_ready = threading.Event()


def current_ports() -> tuple[int, int] | None:
    """Return the bridge's bound (WebSocket, HTTP) ports, or None when down."""
    return _current_ports


def _broadcast(payload: dict[str, typ.Any]) -> None:
    """Submit a broadcast to the bridge event loop from any thread."""
    loop = _bridge_loop
    if loop is None:
        return
    coroutine = _async_broadcast(payload)
    try:
        asyncio.run_coroutine_threadsafe(coroutine, loop)
    except RuntimeError:
        coroutine.close()


async def _async_broadcast(payload: dict[str, typ.Any]) -> None:
    """Send one payload to every connected editor, dropping dead peers."""
    if not _clients:
        return
    msg = json.dumps(payload, ensure_ascii=False)
    dead: set[typ.Any] = set()
    for ws in _clients:
        try:
            await ws.send(msg)
        except Exception:  # ruff: ignore[blind-except]  # a failed peer must not stop the loop
            dead.add(ws)
    _clients.difference_update(dead)


def notify_scene_update(scene: VoxelScene) -> None:
    """Tell every connected editor that ``scene`` has changed."""
    _broadcast({"type": "scene_update", "scene": scene.to_dict()})


async def _send_scene(
    websocket: typ.Any,  # ruff: ignore[any-type]  # no stable public websockets type
    name: str | None,
) -> None:
    """Send one scene snapshot, or nothing when the named scene is absent."""
    if name and name in store._scenes:
        await websocket.send(
            json.dumps(
                {"type": "scene_update", "scene": store._scenes[name].to_dict()},
                ensure_ascii=False,
            )
        )


async def _apply_editor_place(msg: dict[str, typ.Any]) -> None:
    """Place one voxel on behalf of the editor, then broadcast the scene."""
    scene = store.get(msg.get("scene_name"))
    scene.place(
        int(msg["x"]),
        int(msg["y"]),
        int(msg["z"]),
        str(msg.get("color", "1")),
        msg.get("layer_index"),
    )
    await _async_broadcast({"type": "scene_update", "scene": scene.to_dict()})


async def _apply_editor_remove(msg: dict[str, typ.Any]) -> None:
    """Remove one voxel on behalf of the editor, then broadcast the scene."""
    scene = store.get(msg.get("scene_name"))
    scene.remove(
        int(msg["x"]),
        int(msg["y"]),
        int(msg["z"]),
        msg.get("layer_index"),
    )
    await _async_broadcast({"type": "scene_update", "scene": scene.to_dict()})


_WS_POLICY_VIOLATION = 1008


def _ws_origin_allowed(
    websocket: typ.Any,  # ruff: ignore[any-type]  # no stable public websockets type
) -> bool:
    """Check a connection's Origin header against the allowed origins.

    Origins are checked per connection rather than at serve time because
    the allowed set grows when a supervised editor reports its port.
    """
    request = getattr(websocket, "request", None)
    headers = getattr(request, "headers", None)
    origin = headers.get("Origin") if headers is not None else None
    return origin is None or origin in allowed_origins()


async def _ws_handler(
    websocket: typ.Any,  # ruff: ignore[any-type]  # no stable public websockets type
) -> None:
    """Serve one editor websocket connection until the peer goes away."""
    if not _ws_origin_allowed(websocket):
        await websocket.close(_WS_POLICY_VIOLATION, "origin is not allowed")
        return
    _clients.add(websocket)
    try:
        await _send_scene(websocket, store._current)
        async for raw in websocket:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            match msg.get("type"):
                case "get_scene":
                    await _send_scene(websocket, msg.get("name") or store._current)
                case "editor_place":
                    await _apply_editor_place(msg)
                case "editor_remove":
                    await _apply_editor_remove(msg)
    finally:
        _clients.discard(websocket)


def _bound_port(server: typ.Any, requested: int) -> int:  # ruff: ignore[any-type]  # accepts asyncio and websockets servers
    """Read the port a server actually bound, falling back to the request."""
    sockets = getattr(server, "sockets", None)
    if sockets:
        return int(sockets[0].getsockname()[1])
    return requested


async def _run_servers(ws_port: int = 0, http_port: int = 0) -> None:
    """Run the websocket and HTTP servers until the task is cancelled.

    Both ports default to ``0`` so the operating system assigns free
    ephemeral ones; the bound ports are published through
    :func:`current_ports`. Origins are enforced per connection in the
    handlers, so an editor port registered after startup is honoured.
    """
    global _bridge_loop, _current_ports

    import websockets

    ws_server = await websockets.serve(_ws_handler, BRIDGE_HOST, ws_port)
    http_server = await asyncio.start_server(_http_handler, BRIDGE_HOST, http_port)
    bound_ws = _bound_port(ws_server, ws_port)
    bound_http = _bound_port(http_server, http_port)
    _bridge_loop = asyncio.get_running_loop()
    _current_ports = (bound_ws, bound_http)
    _ready.set()
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


_bridge_thread: threading.Thread | None = None


_STARTUP_TIMEOUT_SECONDS = 10.0


def start_bridge_background() -> tuple[int, int]:
    """Start the bridge on a daemon thread unless it is already running.

    Returns
    -------
    tuple[int, int]
        The (WebSocket, HTTP) ports the bridge bound. Ephemeral ports are
        requested, so two concurrent VoxelForge instances never collide.

    Raises
    ------
    RuntimeError
        If the bridge does not report readiness within its startup
        timeout.
    """
    global _bridge_thread
    with _lock:
        if not (_bridge_thread and _bridge_thread.is_alive()):

            def run() -> None:
                asyncio.run(_run_servers())

            _bridge_thread = threading.Thread(target=run, daemon=True)
            _bridge_thread.start()
    if not _ready.wait(_STARTUP_TIMEOUT_SECONDS):
        msg = "the bridge did not report readiness in time"
        raise RuntimeError(msg)
    ports = _current_ports
    if ports is None:
        msg = "the bridge started but published no ports"
        raise RuntimeError(msg)
    return ports


def main() -> None:
    """Run the bridge in the foreground on fixed, configurable ports."""
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


from voxel_forge.bridge_http import (  # ruff: ignore[module-import-not-at-top-of-file]  # the HTTP module needs the bridge state above
    _http_handler,
)

if __name__ == "__main__":
    main()
