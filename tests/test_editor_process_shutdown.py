"""Contract tests for bounded shutdown of supervised editor processes."""

from __future__ import annotations

import logging
import subprocess  # ruff: ignore[suspicious-subprocess-import]  # fixed interpreter and inline code; shell=False
import sys

import pytest

from voxel_forge.orchestration import stop_editor_process


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX SIGTERM ignore fixture")
def test_shutdown_kills_child_that_ignores_terminate(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A child that ignores terminate must be killed and reaped after timeout."""
    caplog.set_level(logging.INFO, logger="voxel_forge.orchestration")
    code = (
        "import signal, time; "
        "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        "print('ready', flush=True); time.sleep(60)"
    )
    with subprocess.Popen(  # ruff: ignore[subprocess-without-shell-equals-true]  # fixed interpreter and inline code; shell=False
        [sys.executable, "-c", code],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    ) as process:
        try:
            assert process.stdout is not None, "capture the child's readiness marker"
            assert process.stdout.readline().strip() == "ready", (
                "install the signal handler before requesting shutdown"
            )
            stop_editor_process(process, timeout=0.1)
            assert process.poll() is not None, (
                "kill escalation must reap the real child"
            )
            assert any(
                record.getMessage().startswith("Editor terminate timed out; escalating")
                for record in caplog.records
            ), "report that graceful shutdown required escalation"
        finally:
            if process.poll() is None:
                stop_editor_process(process, timeout=0.1)
