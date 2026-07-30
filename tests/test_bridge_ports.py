"""Contract tests for dynamic bridge ports and derived editor origins.

Roadmap task 1.2.3: the bridge binds ephemeral ports instead of fixed
ones, publishes what it bound, and derives the permitted editor origin
from the discovered editor port rather than from a constant.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import socket
import subprocess  # ruff: ignore[suspicious-subprocess-import]  # tests spawn python instances with fixed args; shell=False
import sys
import typing as typ
import urllib.request

if typ.TYPE_CHECKING:
    import pytest

from voxel_forge import bridge

_FIXED_PORTS = (8765, 8766, 5173)


def _occupy(port: int) -> socket.socket | None:
    """Bind a loopback port to simulate another service holding it."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", port))
    except OSError:
        sock.close()
        return None
    sock.listen(1)
    return sock


def test_bridge_starts_with_all_fixed_ports_occupied() -> None:
    """The bridge must start even when 8765, 8766 and 5173 are taken."""
    occupied = [sock for port in _FIXED_PORTS if (sock := _occupy(port))]
    try:
        ws_port, http_port = bridge.start_bridge_background()

        assert ws_port not in _FIXED_PORTS, "the WebSocket port must be ephemeral"
        assert http_port not in _FIXED_PORTS, "the HTTP port must be ephemeral"
        with urllib.request.urlopen(  # fixed loopback URL scheme
            f"http://127.0.0.1:{http_port}/health", timeout=10
        ) as response:
            health = json.loads(response.read())
        assert health["ok"] is True, "the bridge health endpoint must answer"
    finally:
        for sock in occupied:
            sock.close()


def test_two_instances_run_concurrently() -> None:
    """Two VoxelForge processes must start bridges without colliding."""
    script = (
        "from voxel_forge.bridge import start_bridge_background\n"
        "print(*start_bridge_background())\n"
    )
    with (
        subprocess.Popen(  # ruff: ignore[subprocess-without-shell-equals-true]  # fixed interpreter and script; shell=False
            [sys.executable, "-c", script],
            stdout=subprocess.PIPE,
            text=True,
        ) as first,
        subprocess.Popen(  # ruff: ignore[subprocess-without-shell-equals-true]  # fixed interpreter and script; shell=False
            [sys.executable, "-c", script],
            stdout=subprocess.PIPE,
            text=True,
        ) as second,
    ):
        outputs = [process.communicate(timeout=30)[0] for process in (first, second)]

        port_pairs = [tuple(int(port) for port in out.split()) for out in outputs]
        assert first.returncode == 0, "the first instance must start its bridge"
        assert second.returncode == 0, "the second instance must start its bridge"
        assert port_pairs[0] != port_pairs[1], "concurrent instances must not collide"


def test_allowed_origins_follow_registered_editor_port() -> None:
    """Registering a discovered editor port must extend the allowed origins."""
    probe_port = 45999
    origin = f"http://127.0.0.1:{probe_port}"
    assert origin not in bridge.allowed_origins(), "probe port must start unknown"

    bridge.register_editor_origin(probe_port)

    assert origin in bridge.allowed_origins(), (
        "the registered port must be an allowed origin"
    )
    assert f"http://localhost:{probe_port}" in bridge.allowed_origins(), (
        "the localhost form must be allowed as well"
    )


class _FakeWebSocket:
    """A websocket double carrying an Origin header and recording close()."""

    def __init__(self, origin: str | None) -> None:
        headers = {} if origin is None else {"Origin": origin}
        self.request = type("Request", (), {"headers": headers})()
        self.closed_with: tuple[int, str] | None = None

    async def close(self, code: int, reason: str) -> None:
        self.closed_with = (code, reason)

    def __aiter__(self) -> typ.Self:
        return self

    async def __anext__(self) -> str:
        raise StopAsyncIteration

    async def send(self, _message: str) -> None:
        """Accept a message silently, as the real socket would."""


def test_ws_handler_rejects_unknown_origin() -> None:
    """A websocket peer with a foreign origin must be closed, not served."""
    websocket = _FakeWebSocket("https://example.invalid")

    asyncio.run(bridge._ws_handler(websocket))

    assert websocket.closed_with is not None, "the connection must be closed"
    assert websocket.closed_with[0] == bridge._WS_POLICY_VIOLATION, (
        "the close code must signal a policy violation"
    )


def test_ws_handler_accepts_registered_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    """A websocket peer from a registered editor origin must be served."""
    monkeypatch.setattr(bridge, "store", bridge.SceneStore())
    bridge.register_editor_origin(46001)
    websocket = _FakeWebSocket("http://127.0.0.1:46001")

    with contextlib.suppress(StopAsyncIteration):
        asyncio.run(bridge._ws_handler(websocket))

    assert websocket.closed_with is None, "an allowed origin must not be closed"
