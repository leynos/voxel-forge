"""Contracts for supervised editor wiring, reuse, and concurrent launch calls."""

from __future__ import annotations

import concurrent.futures
import subprocess  # ruff: ignore[suspicious-subprocess-import]  # fixed interpreter fixture children; shell=False
import sys
import threading
import typing as typ

import pytest

from voxel_forge import bridge, orchestration, server
from voxel_forge.orchestration import EditorPorts, stop_editor_process
from voxel_forge.server_tools import io

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    from pathlib import Path


@pytest.fixture
def editor_child() -> cabc.Iterator[subprocess.Popen[str]]:
    """Own a long-running child whose shutdown can be observed."""
    with subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        text=True,
    ) as child:
        try:
            yield child
        finally:
            stop_editor_process(child)


def _prepare_launch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> list[str]:
    """Isolate persistent state and browser effects without replacing runtime wiring."""
    import webbrowser

    monkeypatch.setattr(io, "editor_package_root", lambda: tmp_path)
    monkeypatch.setattr(io, "_editor_state", {})
    monkeypatch.setattr(orchestration, "_supervised", {})
    monkeypatch.setattr(bridge, "_editor_origin_ports", {5173})
    monkeypatch.setattr(bridge, "current_ports", lambda: (43001, 43002))
    monkeypatch.setattr(server, "_ensure_bridge", lambda _trigger: None)
    opened: list[str] = []
    monkeypatch.setattr(webbrowser, "open", opened.append)
    return opened


def test_launch_integrates_install_supervision_and_origin(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    editor_child: subprocess.Popen[str],
) -> None:
    """First launch must install dependencies and connect the real runtime adapters."""
    opened = _prepare_launch(monkeypatch, tmp_path)
    installed: list[Path] = []
    started: list[EditorPorts] = []

    def install() -> Path:
        """Record dependency installation without invoking the network."""
        installed.append(tmp_path)
        return tmp_path

    def start(ports: EditorPorts) -> tuple[subprocess.Popen[str], int]:
        """Record advertised endpoints while supplying the owned test process."""
        started.append(ports)
        return editor_child, 45991

    monkeypatch.setattr(io, "install_editor_dependencies", install)
    monkeypatch.setattr(io, "start_editor_process", start)
    assert not (tmp_path / "node_modules").exists(), "exercise first-time installation"

    response = io.voxelforge_launch_editor()

    assert installed == [tmp_path], "install missing editor dependencies"
    assert started == [EditorPorts(43001, 43002)], (
        "advertise the discovered bridge ports"
    )
    assert orchestration._supervised == {editor_child.pid: editor_child}, (
        "register the actual process for interpreter-exit supervision"
    )
    assert "http://127.0.0.1:45991" in bridge.allowed_origins(), (
        "register the discovered editor origin"
    )
    assert io._editor_state["editor"] == (editor_child, 45991, (43001, 43002)), (
        "retain process and bridge endpoints for reuse decisions"
    )
    assert opened == ["http://127.0.0.1:45991"], "open the discovered editor URL"
    assert opened[0] in response, "report the same URL to the caller"


def test_bridge_port_change_stops_stale_editor(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    editor_child: subprocess.Popen[str],
) -> None:
    """A replacement editor must advertise the new bridge and revoke the old origin."""
    _prepare_launch(monkeypatch, tmp_path)
    (tmp_path / "node_modules").mkdir()
    observed: list[EditorPorts] = []
    with subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        text=True,
    ) as replacement:

        def start(ports: EditorPorts) -> tuple[subprocess.Popen[str], int]:
            """Supply a distinct child for each bridge configuration."""
            observed.append(ports)
            return (editor_child, 45990) if len(observed) == 1 else (replacement, 45991)

        monkeypatch.setattr(io, "start_editor_process", start)
        try:
            io.voxelforge_launch_editor()
            monkeypatch.setattr(bridge, "current_ports", lambda: (43003, 43004))
            io.voxelforge_launch_editor()
            assert editor_child.poll() is not None, "stop the obsolete editor"
            assert replacement.poll() is None, "keep the replacement editor alive"
            assert "http://127.0.0.1:45990" not in bridge.allowed_origins(), (
                "revoke the old editor origin"
            )
            assert "http://127.0.0.1:45991" in bridge.allowed_origins(), (
                "permit the replacement editor"
            )
            assert observed == [EditorPorts(43001, 43002), EditorPorts(43003, 43004)], (
                "restart using the new bridge endpoints"
            )
        finally:
            stop_editor_process(replacement)


def test_concurrent_launches_start_one_editor(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    editor_child: subprocess.Popen[str],
) -> None:
    """Concurrent tool calls must share one process and its discovered port."""
    _prepare_launch(monkeypatch, tmp_path)
    (tmp_path / "node_modules").mkdir()
    starting = threading.Event()
    release = threading.Event()
    observed: list[EditorPorts] = []

    def start(ports: EditorPorts) -> tuple[subprocess.Popen[str], int]:
        """Hold startup so a second caller can attempt a concurrent launch."""
        observed.append(ports)
        starting.set()
        assert release.wait(timeout=5), "the test must release editor startup"
        return editor_child, 45990

    monkeypatch.setattr(io, "start_editor_process", start)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(io.voxelforge_launch_editor)]
        try:
            assert starting.wait(timeout=5), "the first caller must reach startup"
            assert io._editor_lock.locked(), "startup must hold the lifecycle lock"
            futures.append(pool.submit(io.voxelforge_launch_editor))
        finally:
            release.set()
        responses = [future.result(timeout=5) for future in futures]
    assert len(observed) == 1, "only one caller may spawn the shared editor"
    assert responses[0] == responses[1], "both callers must receive the same editor URL"


def test_unexpected_exit_revokes_origin_and_reports_restart(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    editor_child: subprocess.Popen[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An exited child must lose its old allowance before a later restart."""
    _prepare_launch(monkeypatch, tmp_path)
    monkeypatch.setattr(
        io,
        "_editor_state",
        {
            "editor": (editor_child, 45992, (43001, 43002)),
        },
    )
    monkeypatch.setattr(bridge, "_editor_origin_ports", {5173, 45992})
    editor_child.terminate()
    editor_child.wait(timeout=5)

    assert io._running_editor() is None, "discard an unexpectedly exited child"
    assert "http://127.0.0.1:45992" not in bridge.allowed_origins(), (
        "revoke the stale origin"
    )
    assert not io._editor_state, "release the obsolete process state"
    assert any(
        record.getMessage().startswith("Editor exited unexpectedly")
        for record in caplog.records
    ), "record the exit and planned restart"
