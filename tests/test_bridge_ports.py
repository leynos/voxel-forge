"""Contract tests for dynamic bridge ports and derived editor origins.

Roadmap task 1.2.3: the bridge binds ephemeral ports instead of fixed
ones, publishes what it bound, and derives the permitted editor origin
from the discovered editor port rather than from a constant.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import contextlib
import json
import subprocess  # ruff: ignore[suspicious-subprocess-import]  # tests spawn python instances with fixed args; shell=False
import sys
import threading
import typing as typ
from pathlib import Path

if typ.TYPE_CHECKING:
    import pytest

from voxel_forge import bridge

_FIXED_PORTS = (8765, 8766, 5173)


def test_bridge_starts_with_all_fixed_ports_occupied() -> None:
    """A fresh bridge must start even when 8765, 8766 and 5173 are taken."""
    fixture = Path(__file__).with_name("bridge_occupied_fixture.py")
    result = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true]  # fixed interpreter and fixture path; shell=False
        [sys.executable, str(fixture)],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    observed = json.loads(result.stdout)
    assert observed["occupied"] > 0, "the fixture must actually occupy fixed ports"
    assert observed["ws_port"] not in _FIXED_PORTS, (
        "WebSocket must bind an ephemeral port"
    )
    assert observed["http_port"] not in _FIXED_PORTS, "HTTP must bind an ephemeral port"
    assert observed["health"]["ok"] is True, (
        "the fresh bridge must answer health checks"
    )


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


def test_allowed_origins_follow_registered_editor_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Registering a discovered editor port must extend the allowed origins."""
    monkeypatch.setattr(bridge, "_editor_origin_ports", set())
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
    monkeypatch.setattr(bridge, "_editor_origin_ports", set())
    bridge.register_editor_origin(46001)
    websocket = _FakeWebSocket("http://127.0.0.1:46001")

    with contextlib.suppress(StopAsyncIteration):
        asyncio.run(bridge._ws_handler(websocket))

    assert websocket.closed_with is None, "an allowed origin must not be closed"


def test_unregister_preserves_standalone_origin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Revoking a dynamic origin must preserve the standalone editor allowance."""
    monkeypatch.setattr(bridge, "_editor_origin_ports", {5173, 45999})
    for port in (45999, 5173):
        bridge.unregister_editor_origin(port)
    assert bridge.allowed_origins() == frozenset({
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    }), "keep only the standalone origin after revocation"


def test_origin_registration_and_snapshots_can_run_concurrently(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tool-thread registration must not invalidate event-loop origin snapshots."""
    monkeypatch.setattr(bridge, "_editor_origin_ports", set())
    start = threading.Barrier(2)

    def register() -> None:
        """Continuously extend the registry while snapshots are being read."""
        start.wait(timeout=5)
        for port in range(40000, 41000):
            bridge.register_editor_origin(port)

    def snapshot() -> None:
        """Read immutable snapshots while the writer changes the registry."""
        start.wait(timeout=5)
        for _ in range(1000):
            origins = bridge.allowed_origins()
            assert len(origins) % 2 == 0, (
                "each registered port must have both host forms"
            )

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(register), pool.submit(snapshot)]
        for future in futures:
            future.result(timeout=10)
    assert len(bridge.allowed_origins()) == 2000, "retain every concurrent registration"
