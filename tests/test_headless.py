"""Contract tests for headless operation (roadmap step 1.3).

A headless or sandboxed run — continuous integration in particular — has
no display, no browser, and no WebSocket peer, so the server must not
bind a port unless the bridge is explicitly requested.
"""

from __future__ import annotations

import subprocess  # ruff: ignore[suspicious-subprocess-import]  # tests spawn python instances with fixed args; shell=False
import sys
import typing as typ

import pytest

from voxel_forge import server

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


def _run_probe(argv: list[str]) -> str:
    """Run ``server.main`` in a fresh interpreter and report bridge ports."""
    result = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true]  # fixed interpreter and script; shell=False
        [sys.executable, "-c", _PROBE_SCRIPT.format(argv=argv)],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    return result.stdout.strip().splitlines()[-1]


def test_headless_server_binds_no_socket() -> None:
    """Without ``--bridge``, the server must start no listener at all."""
    assert _run_probe([]) == "None", "a default run must leave the bridge down"


def test_bridge_flag_starts_the_listener() -> None:
    """With ``--bridge``, the bridge must come up and publish its ports."""
    assert _run_probe(["--bridge"]) != "None", (
        "--bridge must start the listener eagerly"
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
