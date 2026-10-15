"""Executable contract for the readiness gates.

Each test here pins one behaviour that "basic agent-driven voxel scene creation"
depends on: the MCP launcher, bridge scheduling and origin checks, editor
removal round-trips, scene-name and payload validation, resource bounds,
persistence, and the raw structure of exported MagicaVoxel files.

Run the whole module with ``uv run pytest -q``. Tests that touch persistence
request the ``scene_directory`` fixture from ``conftest.py`` so no real
``~/.voxel-forge`` directory is read or written. Assertions carry messages
because a readiness failure should name the broken contract directly.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import contextlib
import sys
import threading
import typing as typ

if typ.TYPE_CHECKING:
    import collections.abc as cabc


from pathlib import Path
from types import SimpleNamespace

import pytest
from readiness_helpers import EditorSocket, exchange_http, probe_lock

from voxel_forge import bridge
from voxel_forge.model import SceneStore

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_http_bridge_rejects_non_local_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    """The HTTP bridge must refuse remote-origin scene creation without mutation."""
    store = SceneStore()
    monkeypatch.setattr(bridge, "store", store)
    payload = b'{"name":"hostile"}'
    request = (
        b"POST /scene HTTP/1.1\r\n"
        b"Host: 127.0.0.1:8766\r\n"
        b"Origin: https://example.invalid\r\n"
        + f"Content-Length: {len(payload)}\r\n\r\n".encode()
        + payload
    )

    response = exchange_http(request)

    assert response.startswith(b"HTTP/1.1 403 Forbidden"), (
        "a non-local origin must be refused"
    )
    assert store.list_active() == [], "a refused request must not create a scene"


def test_http_bridge_rejects_oversized_body(monkeypatch: pytest.MonkeyPatch) -> None:
    """The HTTP bridge must reject a request body beyond its configured limit."""
    monkeypatch.setattr(bridge, "store", SceneStore())
    request = (
        b"POST /scene HTTP/1.1\r\nHost: 127.0.0.1:87"
        b"66\r\nContent-Length: 10000001\r\n\r\n"
    )

    response = exchange_http(request)

    assert response.startswith(b"HTTP/1.1 413"), (
        "a body over MAX_HTTP_BODY_BYTES must be refused"
    )


def test_bridge_diagnostic_uses_stderr(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Bridge startup diagnostics must stay off the MCP protocol's stdout."""

    class DummyServer:
        async def __aenter__(self) -> DummyServer:
            """Allow the patched server to be used as an async context manager."""
            return self

        async def __aexit__(self, *_args: object) -> None:
            """Close the patched server context without additional work."""
            return

    async def make_server(*_args: object, **_kwargs: object) -> DummyServer:
        """Return the inert context manager used to exercise startup logging."""
        servers: asyncio.Queue[DummyServer] = asyncio.Queue()
        servers.put_nowait(DummyServer())
        return await servers.get()

    monkeypatch.setitem(sys.modules, "websockets", SimpleNamespace(serve=make_server))
    monkeypatch.setattr(asyncio, "start_server", make_server)

    async def run_until_started() -> None:
        """Start the bridge until it logs, then cancel its server task."""
        task = asyncio.create_task(bridge._run_servers())
        await asyncio.sleep(0)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    asyncio.run(run_until_started())
    captured = capsys.readouterr()

    assert not captured.out, (
        "the bridge must not write to stdout, which carries MCP protocol data"
    )
    assert "VoxelForge bridge:" in captured.err, (
        "the bridge must announce its ports on stderr"
    )


def test_editor_place_and_mcp_place_interleave_without_losing_updates(
    monkeypatch: pytest.MonkeyPatch,
    editor_bridge: tuple[SceneStore, asyncio.Queue[dict[str, typ.Any]]],
) -> None:
    """Deterministic interleaving: an editor edit lands between two MCP edits.

    The MCP tool surface and the editor bridge must share one lock, or an
    editor edit can slip into the middle of an MCP read-modify-snapshot
    sequence. The editor's placement is driven from a second thread while the
    main thread holds the lock, so the test fails if the two sides do not
    synchronize on the same store.
    """
    shared, observed = editor_bridge
    scene = shared.create("shared")

    at_parse = threading.Event()
    proceed = threading.Event()

    def hooked_coordinate(_message: dict[str, typ.Any]) -> tuple[int, int, int]:
        """Pause parsing so the test can inspect shared-lock ownership."""
        at_parse.set()
        assert proceed.wait(timeout=5), "the main thread must release the editor hook"
        return 9, 0, 0

    monkeypatch.setattr(bridge, "_block_coordinate", hooked_coordinate)

    def editor_edit() -> None:
        """Run the async WebSocket handler on the editor worker thread."""
        asyncio.run(
            bridge._ws_handler(
                EditorSocket([
                    (
                        '{"type":"editor_place","scene_name":"shared","laye'
                        'r_index":0,"x":9,"y":0,"z":0,"color":"2"}'
                    )
                ])
            )
        )

    scene.place(0, 0, 0, "1")
    thread = threading.Thread(target=editor_edit)
    thread.start()
    assert at_parse.wait(timeout=5), "the editor thread must reach the coordinate parse"
    with probe_lock(shared.lock) as is_available:
        handler_holds_lock = not is_available
    proceed.set()
    thread.join(timeout=5)
    assert not thread.is_alive(), "the editor thread must finish"

    assert handler_holds_lock, (
        "the editor must hold the shared lock across the mutation, not only the lookup"
    )
    assert scene.block_count() == 2, (
        "an editor placement must land alongside the MCP placement"
    )
    assert not observed.empty(), "the editor must broadcast a snapshot"
    assert scene.layer.blocks[0, 0, 0] == "1", "the first MCP voxel must survive"
    assert scene.layer.blocks[9, 0, 0] == "2", "the editor voxel must retain its colour"
    assert observed.get_nowait()["scene"] == scene.to_dict(), (
        "the editor must broadcast the complete merged state"
    )


@pytest.mark.parametrize("state", ["not-started", "scheduled", "failed"])
def test_broadcast_delivery_lifecycle(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], state: str
) -> None:
    """Submit only on a ready loop, and report failed submissions privately."""
    submitted: list[tuple[object, object]] = []
    loop = None if state == "not-started" else object()
    monkeypatch.setattr(bridge, "_bridge_loop", loop)

    def submit(
        coroutine: cabc.Coroutine[object, object, None], target: object
    ) -> concurrent.futures.Future[None]:
        """Record submission and complete its owned coroutine and result."""
        submitted.append((coroutine, target))
        coroutine.close()
        future: concurrent.futures.Future[None] = concurrent.futures.Future()
        if state == "failed":
            future.set_exception(RuntimeError("editor socket went away"))
        else:
            future.set_result(None)
        return future

    monkeypatch.setattr(asyncio, "run_coroutine_threadsafe", submit)
    bridge._broadcast({"type": "scene_update", "scene": {"name": "hidden-payload"}})
    captured = capsys.readouterr()
    assert not captured.out, "broadcasts must never contaminate protocol stdout"
    if state == "not-started":
        assert not submitted, "a missing bridge loop must not submit work"
    else:
        assert len(submitted) == 1, "a ready loop must receive one coroutine"
        assert submitted[0][1] is loop, "the coroutine must use the bridge loop"
    if state == "failed":
        assert "broadcast failed" in captured.err, "a failed future must be reported"
        assert "hidden-payload" not in captured.err, (
            "diagnostics must keep payloads private"
        )
    else:
        assert not captured.err, "ordinary publication must not report an error"


@pytest.mark.parametrize(
    "request_bytes",
    [
        b"POST /scene HTTP/1.1\r\nContent-Length: nope\r\n\r\n",
        b"POST /scene HTTP/1.1\r\nContent-Length: -1\r\n\r\n",
        b"POST /scene HTTP/1.1\r\nContent-Length: 1\r\n\r\n\xff",
    ],
)
def test_http_bridge_returns_400_for_malformed_requests(request_bytes: bytes) -> None:
    """Invalid body framing or encoding must produce a complete HTTP response."""
    from voxel_forge import bridge_http

    async def exchange() -> bytes:
        """Send malformed bytes to a temporary server with a bounded response wait."""
        listener = await asyncio.start_server(bridge_http._http_handler, "127.0.0.1", 0)
        async with listener:
            port = listener.sockets[0].getsockname()[1]
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            try:
                writer.write(request_bytes)
                await writer.drain()
                return await asyncio.wait_for(reader.read(), timeout=1)
            finally:
                writer.close()
                await writer.wait_closed()

    assert asyncio.run(exchange()).startswith(b"HTTP/1.1 400 Bad Request"), (
        "malformed client input must be answered with 400"
    )


def test_bridge_startup_failure_preserves_cause_without_timeout(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A failed listener bind must wake the starter immediately with its cause."""
    failure = OSError("listener bind failed")

    async def fail_start() -> None:
        """Simulate an awaited listener bind failing on the bridge event loop."""
        result: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        result.set_exception(failure)
        await result

    monkeypatch.setattr(bridge, "_bridge_thread", None)
    monkeypatch.setattr(bridge, "_ready", threading.Event())
    monkeypatch.setattr(bridge, "_startup_finished", threading.Event())
    monkeypatch.setattr(bridge, "_startup_error", None)
    monkeypatch.setattr(bridge, "_run_servers", fail_start)
    monkeypatch.setattr(bridge, "_STARTUP_TIMEOUT_SECONDS", 0.1)
    with pytest.raises(RuntimeError, match="bridge failed to start") as caught:
        bridge.start_bridge_background()
    assert caught.value.__cause__ is failure, "preserve the original bind exception"
    assert any(
        record.getMessage() == "Bridge startup failed (OSError)"
        for record in caplog.records
    ), "record the failed startup without logging client data"
