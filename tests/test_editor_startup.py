"""Regression tests for failed editor starts and supervision registration."""

from __future__ import annotations

import subprocess  # ruff: ignore[suspicious-subprocess-import]  # fixed Python fixture command, shell=False
import sys

import pytest

from voxel_forge import editor_runtime, orchestration
from voxel_forge.editor_runtime import EditorRuntimeError
from voxel_forge.orchestration import EditorPorts


@pytest.mark.parametrize(
    "failure",
    [
        EditorRuntimeError("bad listening event"),
        KeyboardInterrupt("startup interrupted"),
    ],
)
def test_startup_failure_reaps_child(
    monkeypatch: pytest.MonkeyPatch,
    failure: BaseException,
) -> None:
    """A child spawned before any readiness exception must be stopped and reaped."""
    with subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        stdout=subprocess.PIPE,
        text=True,
    ) as process:

        def spawn(_executable: str, _ports: EditorPorts) -> subprocess.Popen[str]:
            """Return the child whose lifetime this test owns."""
            return process

        def fail_wait(_process: subprocess.Popen[str], _timeout: float) -> int:
            """Simulate a malformed readiness event or interrupted startup."""
            raise failure

        monkeypatch.setattr(orchestration, "_spawn_editor", spawn)
        monkeypatch.setattr(orchestration, "_wait_for_port", fail_wait)
        try:
            with pytest.raises(type(failure), match=str(failure)):
                orchestration.start_editor_process(EditorPorts(1, 2))
            assert process.poll() is not None, "startup failure must reap its child"
        finally:
            orchestration.stop_editor_process(process)


def test_supervise_discards_exited_processes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Registering a replacement must release obsolete process handles."""
    monkeypatch.setattr(orchestration, "_supervised", {})
    with subprocess.Popen(
        [sys.executable, "-c", "import sys; sys.stdin.read()"],
        stdin=subprocess.PIPE,
        text=True,
    ) as exited:
        orchestration.supervise(exited)
        assert exited.pid in orchestration._supervised, "register the live child"
        assert exited.stdin is not None, "the child must have its private wait pipe"
        exited.stdin.close()
        exited.wait(timeout=5)
        orchestration.supervise(exited)
        assert exited.pid not in orchestration._supervised, (
            "an exited child must not remain registered for interpreter shutdown"
        )


def test_archive_resources_report_unsupported_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bun requires durable filesystem assets rather than archive Traversables."""
    monkeypatch.setattr(editor_runtime.resources, "files", lambda _name: object())
    with pytest.raises(EditorRuntimeError, match="filesystem-backed"):
        editor_runtime.editor_entrypoint()


def test_malformed_listening_event_reaps_child(monkeypatch: pytest.MonkeyPatch) -> None:
    """Invalid readiness payloads must not leave a live process behind."""
    with subprocess.Popen(
        [
            sys.executable,
            "-c",
            (
                "import json, time; "
                "print(json.dumps(dict(event='listening', port='invalid')), "
                "flush=True); "
                "time.sleep(60)"
            ),
        ],
        stdout=subprocess.PIPE,
        text=True,
    ) as process:

        def spawn(_executable: str, _ports: EditorPorts) -> subprocess.Popen[str]:
            """Return the child publishing the malformed readiness event."""
            return process

        monkeypatch.setattr(orchestration, "_spawn_editor", spawn)
        try:
            with pytest.raises(EditorRuntimeError, match="Invalid listening event"):
                orchestration.start_editor_process(EditorPorts(1, 2), startup_timeout=1)
            assert process.poll() is not None, "reap the malformed-event child"
        finally:
            orchestration.stop_editor_process(process)
