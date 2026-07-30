"""Contract tests for headless operation (roadmap step 1.3).

A headless or sandboxed run — continuous integration in particular — has
no display, no browser, and no WebSocket peer, so the server must not
bind a port unless the bridge is explicitly requested.
"""

from __future__ import annotations

import subprocess  # ruff: ignore[suspicious-subprocess-import]  # tests spawn python instances with fixed args; shell=False
import sys
import typing as typ

if typ.TYPE_CHECKING:
    import pytest

from voxel_forge import server

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


def test_scene_mutations_never_start_the_bridge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Editing a scene must notify a running bridge, never start one."""
    calls: list[str] = []
    monkeypatch.setattr(server, "store", server.SceneStore())
    monkeypatch.setattr(
        server, "start_bridge_background", lambda: calls.append("start")
    )
    monkeypatch.setattr(server, "current_ports", lambda: None)

    server.voxelforge_create_scene("headless")
    server.voxelforge_place_block(0, 0, 0, "1")

    assert not calls, "scene mutations must not start the bridge"


def test_notifications_flow_when_a_bridge_is_running(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With a bridge up, scene mutations must still notify subscribers."""
    notified: list[str] = []
    monkeypatch.setattr(server, "store", server.SceneStore())
    monkeypatch.setattr(server, "current_ports", lambda: (1, 2))
    monkeypatch.setattr(
        server, "notify_scene_update", lambda scene: notified.append(scene.name)
    )

    server.voxelforge_create_scene("attended")

    assert notified == ["attended"], "a running bridge must receive updates"
