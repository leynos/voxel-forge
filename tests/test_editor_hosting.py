"""Contract tests for hosting the web editor as a supervised Bun process.

These cover roadmap step 1.2: the editor travels inside the wheel, is
resolvable from both checkout and installed layouts, and is served by Bun
on a discoverable port.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import shutil
import signal
import socket
import subprocess  # ruff: ignore[suspicious-subprocess-import]  # tests spawn Bun with validated arguments and shell=False
import sys
import time
import tomllib
import typing as typ
import urllib.request
from pathlib import Path

import pytest

from voxel_forge import orchestration
from voxel_forge.editor_runtime import (
    EditorRuntimeError,
    editor_entrypoint,
    editor_package_root,
)
from voxel_forge.orchestration import (
    EditorPorts,
    reap_supervised,
    start_editor_process,
    stop_editor_process,
    supervise,
)

BUN = shutil.which("bun")
STARTUP_TIMEOUT_SECONDS = 30.0


def test_editor_entrypoint_resolves_in_checkout() -> None:
    """A repository checkout must resolve the Bun entry point."""
    entrypoint = editor_entrypoint()

    assert entrypoint.name == "serve.ts", "entry point must be the Bun server script"
    assert entrypoint.is_file(), "entry point must exist in a checkout"


def test_editor_package_root_contains_manifest_and_lockfile() -> None:
    """The resolved package root must carry package.json and bun.lock."""
    root = editor_package_root()

    assert (root / "package.json").is_file(), "package root must contain package.json"
    assert (root / "bun.lock").is_file(), "package root must contain the Bun lockfile"


def test_wheel_bundles_the_editor() -> None:
    """The wheel build must force-include the editor's runtime files."""
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    force_include = pyproject["tool"]["hatch"]["build"]["targets"]["wheel"][
        "force-include"
    ]

    packaged = set(force_include.values())
    for required in (
        "voxel_forge/editor/index.html",
        "voxel_forge/editor/src",
        "voxel_forge/editor/serve.ts",
        "voxel_forge/editor/package.json",
        "voxel_forge/editor/bun.lock",
    ):
        assert required in packaged, f"wheel must bundle {required}"
    for source in force_include:
        assert Path(source).exists(), f"force-included source {source} must exist"


def _read_listening_port(process: subprocess.Popen[str]) -> int:
    """Read the structured listening event from the editor's stdout."""
    stdout = process.stdout
    assert stdout is not None, "editor stdout must be captured"
    line = stdout.readline()
    event = json.loads(line)
    assert event.get("event") == "listening", f"unexpected editor event: {event!r}"
    return int(event["port"])


def _editor_accepts_connections(port: int) -> bool:
    """Return whether the editor still accepts loopback connections."""
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.1):
            return True
    except OSError:
        return False


def _wait_for_editor_to_stop(port: int, timeout: float = 5.0) -> bool:
    """Wait for a stopped editor to release its listening port."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _editor_accepts_connections(port):
            return True
        time.sleep(0.05)
    return False


def _stop_editor_if_still_serving(pid: int | None, port: int | None) -> None:
    """Stop a leaked test editor if its known port is still open."""
    if pid is None or port is None:
        return
    if not _editor_accepts_connections(port):
        return
    with contextlib.suppress(ProcessLookupError):
        os.kill(pid, signal.SIGTERM)


def _start_bun_editor(editor_port: int | None) -> subprocess.Popen[str]:
    """Start Bun with an optional editor port and deterministic bridge endpoints."""
    env = {
        "PATH": "/usr/bin:/bin",
        "VOXELFORGE_BRIDGE_WS_PORT": "18765",
        "VOXELFORGE_BRIDGE_HTTP_PORT": "18766",
    }
    if editor_port is not None:
        env["VOXELFORGE_EDITOR_PORT"] = str(editor_port)
    return subprocess.Popen(  # ruff: ignore[subprocess-without-shell-equals-true]  # fixed executable and script path; shell=False
        [typ.cast("str", BUN), str(editor_entrypoint())],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
        cwd=editor_package_root(),
    )


def test_spawn_editor_passes_requested_bridge_endpoints(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The Bun child receives the selected ports through its explicit environment."""
    entrypoint = tmp_path / "serve.ts"
    observed: dict[str, object] = {}
    process = object()

    def capture_spawn(arguments: list[str], **options: object) -> object:
        """Record the command boundary without launching Bun."""
        observed["arguments"] = arguments
        observed.update(options)
        return process

    monkeypatch.setattr(orchestration, "editor_entrypoint", lambda: entrypoint)
    monkeypatch.setattr(orchestration, "editor_package_root", lambda: tmp_path)
    monkeypatch.setattr(orchestration.subprocess, "Popen", capture_spawn)

    started = orchestration._spawn_editor(
        "bun", EditorPorts(bridge_ws=18765, bridge_http=18766, requested=0)
    )

    assert started is process, "return the process from the spawn boundary"
    assert observed["arguments"] == ["bun", str(entrypoint)], (
        "launch Bun with its entrypoint as a separate argument"
    )
    environment = typ.cast("dict[str, str]", observed["env"])
    assert environment["VOXELFORGE_EDITOR_PORT"] == "0", (
        "request an ephemeral editor port"
    )
    assert environment["VOXELFORGE_BRIDGE_WS_PORT"] == "18765", (
        "advertise the discovered WebSocket port"
    )
    assert environment["VOXELFORGE_BRIDGE_HTTP_PORT"] == "18766", (
        "advertise the discovered HTTP port"
    )
    assert observed.get("shell", False) is False, "never invoke Bun through a shell"


@pytest.mark.skipif(BUN is None, reason="bun is not installed")
def test_bun_uses_the_standalone_port_when_none_is_requested() -> None:
    """The documented standalone Bun command must bind port 5173 by default."""
    with _start_bun_editor(editor_port=None) as process:
        try:
            port = _read_listening_port(process)
            assert port == 5173, "standalone Bun startup must use the documented port"
            with socket.create_connection(("127.0.0.1", port), timeout=5):
                pass
        finally:
            stop_editor_process(process)


@pytest.mark.skipif(BUN is None, reason="bun is not installed")
def test_bun_serves_the_editor_on_an_ephemeral_port() -> None:
    """Bun must bind an ephemeral port, report it, and serve the editor."""
    with _start_bun_editor(editor_port=0) as process:
        try:
            port = _read_listening_port(process)

            with socket.create_connection(("127.0.0.1", port), timeout=5):
                pass
            with urllib.request.urlopen(  # fixed loopback URL scheme
                f"http://127.0.0.1:{port}/", timeout=10
            ) as response:
                page = response.read().decode("utf-8")
            with urllib.request.urlopen(  # fixed loopback URL scheme
                f"http://127.0.0.1:{port}/bridge.json", timeout=10
            ) as response:
                bridge = json.loads(response.read())

            assert "VoxelForge" in page, "served page must be the editor"
            assert bridge["wsUrl"].endswith(":18765"), (
                "bridge.json must republish the WebSocket port from the environment"
            )
            assert bridge["httpUrl"].endswith(":18766"), (
                "bridge.json must republish the HTTP port from the environment"
            )
        finally:
            stop_editor_process(process)


@pytest.mark.skipif(BUN is None, reason="bun is not installed")
def test_editor_stops_when_supervising_python_process_is_killed() -> None:
    """The editor must stop after forced parent termination closes its pipe."""
    fixture = Path(__file__).with_name("editor_supervisor_fixture.py")
    editor_pid: int | None = None
    editor_port: int | None = None
    with subprocess.Popen(  # ruff: ignore[subprocess-without-shell-equals-true]  # fixed Python and fixture paths; shell=False
        [sys.executable, str(fixture)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=Path.cwd(),
    ) as parent:
        try:
            stdout = parent.stdout
            assert stdout is not None, "supervisor fixture stdout must be captured"
            event = json.loads(stdout.readline())
            editor_pid = int(event["pid"])
            editor_port = int(event["port"])
            assert _editor_accepts_connections(editor_port), (
                "the supervised editor must accept connections before parent exit"
            )

            parent.kill()
            parent.wait(timeout=5)

            assert _wait_for_editor_to_stop(editor_port), (
                "the editor must close its port after the supervising process is killed"
            )
        finally:
            if parent.poll() is None:
                parent.kill()
            parent.wait(timeout=5)
            _stop_editor_if_still_serving(editor_pid, editor_port)


FAKE_EDITOR_PORT = 43210


@pytest.fixture
def fake_bun(tmp_path: Path) -> Path:
    """Provide a stub executable that mimics the editor's startup protocol."""
    if sys.platform == "win32":
        pytest.skip("POSIX shell executable fixture")
    script = tmp_path / "fake-bun"
    script.write_text(
        "#!/bin/sh\n"
        f'echo \'{{"event": "listening", "port": {FAKE_EDITOR_PORT}}}\'\n'
        "exec sleep 60\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    return script


def test_start_and_stop_editor_reaps_the_process(
    fake_bun: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Stopping a started editor must leave no orphan process behind."""
    caplog.set_level(logging.INFO, logger="voxel_forge.orchestration")
    process, port = start_editor_process(
        EditorPorts(bridge_ws=1, bridge_http=2), bun_executable=str(fake_bun)
    )

    assert port == FAKE_EDITOR_PORT, "the reported port must come from the event"
    assert process.poll() is None, "the editor must still be running before stop"

    stop_editor_process(process)

    assert process.poll() is not None, "no orphan may remain after stop"
    messages = [record.getMessage() for record in caplog.records]
    assert f"Editor starting pid={process.pid}" in messages, "record editor startup"
    assert f"Editor listening pid={process.pid} port={port}" in messages, (
        "record the bound port"
    )
    assert any(message.startswith("Editor stopped") for message in messages), (
        "record shutdown"
    )


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX shell executable fixture")
def test_start_editor_raises_and_reaps_on_abnormal_exit(tmp_path: Path) -> None:
    """A child that dies without reporting a port must raise and be reaped."""
    script = tmp_path / "broken-bun"
    script.write_text("#!/bin/sh\necho boom\nexit 3\n", encoding="utf-8")
    script.chmod(0o755)

    with pytest.raises(EditorRuntimeError, match="did not report a listening port"):
        start_editor_process(
            EditorPorts(bridge_ws=1, bridge_http=2),
            bun_executable=str(script),
            startup_timeout=5.0,
        )


def test_reap_supervised_stops_registered_processes(fake_bun: Path) -> None:
    """Processes registered for supervision must be stopped by the reaper."""
    process, _port = start_editor_process(
        EditorPorts(bridge_ws=1, bridge_http=2), bun_executable=str(fake_bun)
    )
    supervise(process)

    reap_supervised()

    assert process.poll() is not None, "the reaper must stop supervised processes"


def test_missing_bun_executable_is_reported() -> None:
    """A missing Bun executable must produce an actionable error."""
    with pytest.raises(EditorRuntimeError, match="Bun executable not found"):
        start_editor_process(
            EditorPorts(bridge_ws=1, bridge_http=2),
            bun_executable="/nonexistent/bun",
        )


def test_js_root_command_prints_package_root(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`python -m voxel_forge.js_root` must print the editor package root."""
    from voxel_forge import js_root

    exit_code = js_root.main()
    output = capsys.readouterr().out.strip()

    assert exit_code == 0, "resolution must succeed in a checkout"
    assert (Path(output) / "package.json").is_file(), (
        "the printed path must contain package.json"
    )


def test_install_editor_deps_command_reports_failure(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A failed installation must exit non-zero with a diagnostic."""
    from voxel_forge import install_editor_deps

    def raise_runtime_error() -> Path:
        """Simulate dependency installation failing because Bun is missing."""
        msg = "Bun executable not found: bun"
        raise EditorRuntimeError(msg)

    monkeypatch.setattr(
        install_editor_deps, "install_editor_dependencies", raise_runtime_error
    )

    exit_code = install_editor_deps.main()
    captured = capsys.readouterr()

    assert exit_code == 1, "a failed installation must exit non-zero"
    assert "Bun executable not found" in captured.err, (
        "the diagnostic must name the cause"
    )


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX shell executable fixture")
def test_install_editor_dependencies_targets_the_package_root(
    tmp_path: Path,
) -> None:
    """The install helper must run Bun against the resolved package root."""
    from voxel_forge.orchestration import install_editor_dependencies

    recorder = tmp_path / "args.txt"
    stub = tmp_path / "stub-bun"
    stub.write_text(f'#!/bin/sh\necho "$@" > {recorder}\n', encoding="utf-8")
    stub.chmod(0o755)

    root = install_editor_dependencies(bun_executable=str(stub))

    recorded = recorder.read_text(encoding="utf-8")
    assert (root / "package.json").is_file(), (
        "installation must target the editor package root"
    )
    assert str(root) in recorded, "bun install must receive the package root"
    assert "install" in recorded, "the stub must have been asked to install"
