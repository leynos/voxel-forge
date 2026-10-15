"""Lifecycle diagnostics for bounded editor shutdown escalation."""

from __future__ import annotations

import subprocess  # ruff: ignore[suspicious-subprocess-import]  # only models subprocess timeout errors
import typing as typ

import pytest

from voxel_forge.orchestration import stop_editor_process


class _ShutdownProcess:
    """Model an editor ignoring terminate, with configurable kill behaviour."""

    pid = 12345

    def __init__(self, *, is_unstoppable: bool) -> None:
        """Choose whether kill succeeds; for example is_unstoppable=False stops."""
        self.is_unstoppable = is_unstoppable
        self.is_running = True
        self.returncode: int | None = None

    def poll(self) -> int | None:
        """Return the simulated editor's current exit status."""
        return None if self.is_running else self.returncode

    def terminate(self) -> None:
        """Ignore graceful termination to require the escalation path."""

    def kill(self) -> None:
        """Exit only when the configured process can be killed."""
        if not self.is_unstoppable:
            self.is_running = False
            self.returncode = -9

    def wait(self, timeout: float) -> int:
        """Report a timeout while the simulated child is still running."""
        status = self.poll()
        if status is None:
            raise subprocess.TimeoutExpired("editor", timeout)
        return status


@pytest.mark.parametrize("is_unstoppable", [False, True])
def test_shutdown_reports_escalation_and_failure(
    caplog: pytest.LogCaptureFixture,
    *,
    is_unstoppable: bool,
) -> None:
    """Operators must see escalation and a child surviving the final deadline."""
    process = _ShutdownProcess(is_unstoppable=is_unstoppable)
    stop_editor_process(typ.cast("subprocess.Popen[str]", process), timeout=0.01)
    messages = [record.getMessage() for record in caplog.records]
    assert "Editor terminate timed out; escalating to kill pid=12345" in messages, (
        "report the terminate-to-kill escalation"
    )
    assert (
        "Editor remains alive after terminate and kill pid=12345" in messages
    ) == is_unstoppable, "report failure only when kill did not stop the process"
