"""Contract tests for headless operation (roadmap step 1.3).

A headless or sandboxed run — continuous integration in particular — has
no display, no browser, and no WebSocket peer, so the server must not
bind a port unless the bridge is explicitly requested.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import subprocess  # ruff: ignore[suspicious-subprocess-import]  # tests spawn python instances with fixed args; shell=False
import sys
import typing as typ

import pytest

from voxel_forge import bridge, server

if typ.TYPE_CHECKING:
    from voxel_forge.model import VoxelScene

_PROBE_SCRIPT = """
import sys

from voxel_forge import bridge, server

server.mcp.run = lambda **_kwargs: None
sys.argv = ["voxel-forge-mcp"] + {argv!r}
server.main()
print(bridge.current_ports())
"""


def _probe_environment(bridge_env: str | None) -> dict[str, str]:
    """Build a child environment with ``VOXELFORGE_BRIDGE`` set exactly once.

    The variable is always removed from the inherited environment first, so a
    developer who exports ``VOXELFORGE_BRIDGE=1`` cannot make the default-run
    probe fail, and a row that means to enable the bridge has to say so here
    rather than passing by accident.
    """
    environment = {
        key: value for key, value in os.environ.items() if key != "VOXELFORGE_BRIDGE"
    }
    if bridge_env is not None:
        environment["VOXELFORGE_BRIDGE"] = bridge_env
    return environment


def _probe(
    argv: list[str], *, bridge_env: str | None = None
) -> subprocess.CompletedProcess[str]:
    """Run ``server.main`` in a fresh interpreter and capture both streams."""
    return subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true]  # fixed interpreter and script; shell=False
        [sys.executable, "-c", _PROBE_SCRIPT.format(argv=argv)],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
        env=_probe_environment(bridge_env),
    )


def _run_probe(argv: list[str], *, bridge_env: str | None = None) -> str:
    """Run ``server.main`` in a fresh interpreter and report bridge ports."""
    return _probe(argv, bridge_env=bridge_env).stdout.strip().splitlines()[-1]


@pytest.mark.parametrize(
    ("argv", "bridge_env", "is_listening"),
    [
        ([], None, False),
        (["--bridge"], None, True),
        ([], "1", True),
    ],
    ids=["default-headless", "bridge-flag", "bridge-environment"],
)
def test_bridge_starts_only_when_explicitly_requested(
    argv: list[str],
    bridge_env: str | None,
    is_listening: bool,  # ruff: ignore[boolean-type-hint-positional-argument]  # parametrized row, not a caller-facing flag
) -> None:
    """The bridge must bind only for ``--bridge`` or ``VOXELFORGE_BRIDGE=1``.

    All three rows run the identical probe, so the rows differ only in how the
    bridge is requested. The default row pins the headless contract: a run
    with no request of any kind must leave the listener down.
    """
    ports = _run_probe(argv, bridge_env=bridge_env)

    assert (ports != "None") is is_listening, (
        f"argv={argv!r} with VOXELFORGE_BRIDGE={bridge_env!r} produced {ports!r}"
    )


@pytest.mark.parametrize(
    ("arguments", "expected_fields"),
    [
        ([], "bridge_mode=headless bridge_state=down"),
        (["--bridge"], "bridge_mode=eager bridge_state=running"),
    ],
    ids=["headless", "eager"],
)
def test_startup_reports_the_bridge_mode_on_stderr(
    arguments: list[str],
    expected_fields: str,
) -> None:
    """Startup must state the requested mode and the state it reached.

    A headless run and a run whose bridge never came up look identical to an
    operator without this line: the process blocks on stdio either way. The
    fields are pinned so a log scraper keeps working, and the probe's own
    stdout is inspected to prove the report did not land on the protocol
    stream.
    """
    completed = _probe(arguments)

    assert "operation=server_start" in completed.stderr, (
        "the startup report must carry its operation identifier"
    )
    assert expected_fields in completed.stderr, (
        f"argv={arguments!r} must report {expected_fields!r}, got: {completed.stderr!r}"
    )
    assert "server_start" not in completed.stdout, (
        "startup must not write to stdout, which carries MCP protocol data"
    )


@pytest.mark.parametrize(
    ("arguments", "bridge_env"),
    [
        (["--bridge"], None),
        ([], "1"),
    ],
    ids=["flag", "environment"],
)
def test_the_bridge_start_names_what_requested_it(
    arguments: list[str],
    bridge_env: str | None,
) -> None:
    """A start must name its trigger, so a log reader can separate the paths.

    Both rows are the eager path, reached by the flag or by the environment
    seed. They must be indistinguishable in the log, because the request is the
    same one; the on-demand path is covered by
    ``test_launch_editor_requests_the_bridge``.
    """
    completed = _probe(arguments, bridge_env=bridge_env)

    assert "operation=bridge_start trigger=server_start" in completed.stderr, (
        f"{arguments!r} with VOXELFORGE_BRIDGE={bridge_env!r} must name its "
        f"trigger, got: {completed.stderr!r}"
    )
    assert "bridge_start" not in completed.stdout, (
        "the start diagnostic must stay off the protocol stream"
    )


def test_a_default_run_reports_no_bridge_start() -> None:
    """A headless run must not report a start it never performed.

    The diagnostic is only useful if it is absent exactly when no bridge came
    up; emitting it unconditionally would make it useless for telling the two
    cases apart.
    """
    completed = _probe([])

    assert "operation=bridge_start" not in completed.stderr, (
        f"a headless run must not claim a bridge start, got: {completed.stderr!r}"
    )


def test_launch_editor_requests_the_bridge(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The on-demand path must report its own start, naming the tool that asked.

    This is the start the eager diagnostics cannot describe: nothing in
    ``argv`` requested a bridge, and the listener came up only because an MCP
    client called ``voxelforge_launch_editor``.
    """
    from voxel_forge.server_tools import io

    started: list[str] = []
    monkeypatch.setattr(server, "start_bridge_background", lambda: started.append("s"))
    monkeypatch.setattr(server, "current_ports", lambda: None)
    monkeypatch.setattr(server, "store", server.SceneStore())
    monkeypatch.setattr(io.bridge, "use_store", lambda _store: None)

    io.voxelforge_launch_editor()

    assert started == ["s"], "the tool must request the bridge exactly once"
    assert "operation=bridge_start trigger=launch_editor" in capsys.readouterr().err, (
        "the on-demand start must name the tool that triggered it"
    )


class _StoppableBridge:
    """A real bridge task, alive only while the test lets it run."""

    def __init__(self) -> None:
        """Start nothing; the test starts and cancels the listener itself."""
        self.task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Run the listeners until cancelled, as the bridge thread does."""
        self.task = asyncio.create_task(bridge._run_servers())

    async def stop(self) -> None:
        """Cancel the listeners and let the teardown run to completion."""
        assert self.task is not None, "stop() requires a started bridge"
        self.task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self.task


def test_stopping_the_bridge_reports_the_transition(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A stopped bridge must be reported, not just silently un-published.

    Without this line a bridge that came up and then stopped is indistinguishable
    in the log from one that never came up, because the only bridge diagnostic
    is the endpoint line printed at startup.
    """
    stoppable = _StoppableBridge()

    async def run() -> None:
        await stoppable.start()
        await asyncio.sleep(0.3)
        assert bridge.current_ports() is not None, "the bridge must have bound ports"
        await stoppable.stop()

    asyncio.run(run())
    captured = capsys.readouterr()

    assert bridge.current_ports() is None, "a stopped bridge must publish no ports"
    assert (
        "operation=bridge_state bridge_state=down error_category=CancelledError"
        in captured.err
    ), f"the stop must report the cancelling class, got: {captured.err!r}"
    assert "VoxelForge bridge:" not in captured.out, (
        "bridge diagnostics must stay off the protocol stream"
    )
    assert captured.err.count("bridge_state=down") == 1, (
        "each transition must be reported once, not once per subscriber"
    )


class _BridgeState:
    """Observable stand-in for a bridge that is either up or stopped."""

    def __init__(self) -> None:
        """Start stopped, with nothing started and nothing published."""
        self.is_running = False
        self.started: list[str] = []
        self.notified: list[str] = []

    def start(self) -> None:
        """Record an eager listener start, which a scene edit must never cause."""
        self.started.append("start")
        self.is_running = True

    def ports(self) -> tuple[int, int] | None:
        """Publish ports only while the listener is actually up."""
        return (1, 2) if self.is_running else None

    def notify(self, scene: VoxelScene) -> None:
        """Record the name of the scene whose edit was published."""
        self.notified.append(scene.name)


@pytest.fixture
def bridge_state(monkeypatch: pytest.MonkeyPatch) -> _BridgeState:
    """Replace the server's bridge boundary with an observable stand-in."""
    state = _BridgeState()
    monkeypatch.setattr(server, "store", server.SceneStore())
    monkeypatch.setattr(server, "start_bridge_background", state.start)
    monkeypatch.setattr(server, "current_ports", state.ports)
    monkeypatch.setattr(server, "notify_scene_update", state.notify)
    return state


@pytest.mark.parametrize(
    ("bridge_running", "expected_notified"),
    [(False, []), (True, ["scene"])],
    ids=["headless", "attended"],
)
def test_scene_edits_follow_the_bridge_state(
    bridge_state: _BridgeState,
    bridge_running: bool,  # ruff: ignore[boolean-type-hint-positional-argument]  # parametrized row, not a caller-facing flag
    expected_notified: list[str],
) -> None:
    """An edit must notify a running bridge, and never start a stopped one.

    Both rows perform the identical edit, so a regression that binds a port on
    the first edit of a headless run — or that stops publishing once a bridge
    is up — fails the row whose precondition it violates.
    """
    bridge_state.is_running = bridge_running

    server.voxelforge_create_scene("scene")

    assert not bridge_state.started, "scene edits must not start the bridge"
    assert bridge_state.notified == expected_notified, (
        "only a bridge that is already running may receive an edit"
    )
