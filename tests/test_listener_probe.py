"""Contract tests for the process-scoped listening-socket probe, live processes.

``tests/installed_smoke.py`` asserts that a headless run binds no socket, and
that assertion is only worth anything if the probe underneath it can actually
see a socket. These tests are the probe's controls against *real* processes:
they prove it detects a process that really is listening, that it does not
attribute another process's listener to an idle one, and that an unreadable
process is reported as inconclusive rather than as an empty result.

The synthetic-table controls — a ``/proc`` tree the test writes itself, so the
malformed and unreadable paths can be reached without a misbehaving host — live
in ``tests/test_listener_probe_tables.py``. The driver's use of each answer is a
third question, asked in ``tests/test_smoke_listener_gate.py``.
"""

from __future__ import annotations

import contextlib
import dataclasses
import subprocess  # ruff: ignore[suspicious-subprocess-import]  # spawns fixed interpreter snippets; shell=False
import sys
import time
import typing as typ
from pathlib import Path

if typ.TYPE_CHECKING:
    import collections.abc as cabc

import pytest
from listener_probe import ListenerReport, ProbeOutcome, probe_listeners

# A child that binds, reports its port, and then idles until it is killed.
_LISTENING_CHILD = """
import socket, sys, time

server = socket.socket()
server.bind(("127.0.0.1", 0))
server.listen(1)
print(server.getsockname()[1], flush=True)
time.sleep(30)
"""

_IDLE_CHILD = "import time; time.sleep(30)"

# Linux gates the probe, and /proc must be present for the positive controls.
_NEEDS_PROC = pytest.mark.skipif(
    not Path("/proc").is_dir(), reason="the listener probe needs a Linux /proc"
)


@dataclasses.dataclass(frozen=True, slots=True)
class _ListeningChild:
    """A running child process that holds a known listening port."""

    process: subprocess.Popen[str]
    port: int


def _spawn(program: str) -> subprocess.Popen[str]:
    """Start a child running ``program`` and return it."""
    return subprocess.Popen(  # ruff: ignore[subprocess-without-shell-equals-true]  # fixed snippet, shell=False
        [sys.executable, "-c", program],
        stdout=subprocess.PIPE,
        text=True,
    )


def _kill(process: subprocess.Popen[str]) -> None:
    """Stop a child and reap it, so no test leaves a process behind."""
    process.kill()
    process.wait(10)


@pytest.fixture
def listening_child() -> cabc.Iterator[_ListeningChild]:
    """Start a child that binds a loopback port, and stop it afterwards."""
    process = _spawn(_LISTENING_CHILD)
    assert process.stdout is not None, "the child's port is read from its stdout"
    port = int(process.stdout.readline())
    # Give the socket time to appear in the process's descriptor table.
    time.sleep(0.3)
    try:
        yield _ListeningChild(process, port)
    finally:
        _kill(process)


@contextlib.contextmanager
def _idle_report() -> cabc.Iterator[ListenerReport]:
    """Probe a child that holds no socket, and stop it afterwards.

    The probe reads a live process's tables, so the child has to outlive the
    read and must not outlive the test. Yielding the report rather than the
    process keeps each assertion in the calling test, where its meaning is
    plain.
    """
    idle = _spawn(_IDLE_CHILD)
    try:
        # Give the child time to reach a steady state before it is measured.
        time.sleep(0.3)
        yield probe_listeners(idle.pid)
    finally:
        _kill(idle)


@_NEEDS_PROC
def test_probe_detects_a_real_listener(listening_child: _ListeningChild) -> None:
    """The probe must see a port that a process genuinely bound.

    This is the check that keeps the headless assertion honest: if the probe
    could not observe a listener, every "no listener" result would be vacuous.
    """
    report = probe_listeners(listening_child.process.pid)

    assert report.outcome is ProbeOutcome.MEASURED, (
        "a readable /proc must yield a conclusive answer"
    )
    assert listening_child.port in report.ports, (
        f"the probe missed port {listening_child.port}, which the child had "
        "bound, so any 'no listener' result would be meaningless"
    )


@_NEEDS_PROC
def test_probe_does_not_attribute_another_process_listener(
    listening_child: _ListeningChild,
) -> None:
    """An idle process must not inherit another process's listening port.

    ``ss`` and ``lsof`` report the host, not the process, so attributing a port
    to the wrong process is the failure this scoping exists to prevent.
    """
    with _idle_report() as report:
        assert report.outcome is ProbeOutcome.MEASURED, "the idle child is readable"
        assert listening_child.port not in report.ports, (
            "the probe attributed another process's listener to an idle process"
        )


@_NEEDS_PROC
def test_probe_reports_no_listener_as_a_measured_empty_result() -> None:
    """An idle process must be a conclusive empty answer, not an unknown.

    ``MEASURED`` with no ports is the one result the smoke test treats as
    certification, so it must be reachable only by actually reading the tables.
    """
    with _idle_report() as report:
        assert report.outcome is ProbeOutcome.MEASURED, (
            "an idle process has readable tables, so the probe must answer"
        )
        assert not report.ports, (
            "an idle process holds no listening socket, so it must report none"
        )
        assert not report.reason, "a conclusive answer needs no excuse"


def test_probe_reports_a_missing_process_as_failed() -> None:
    """An unreadable process must be reported as failed, not as silent.

    The distinction is what stops "the check never ran" from being read as
    "the check found nothing".
    """
    report = probe_listeners(999999)

    assert report.outcome is ProbeOutcome.FAILED, (
        "a process with no readable /proc entry cannot be measured"
    )
    assert not report.ports, "an inconclusive answer must carry no ports"
    assert report.reason, "the failure must say what could not be read"


def test_probe_reports_an_absent_proc_as_unsupported(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A host without ``/proc`` must be reported as unsupported, distinctly.

    Unsupported and failed call for different responses from an operator: one
    means the platform cannot run the check, the other means this process could
    not be read. Collapsing them would hide which problem to fix.
    """
    monkeypatch.setattr("listener_probe.PROC_ROOT", tmp_path / "no-such-proc")

    report = probe_listeners(1)

    assert report.outcome is ProbeOutcome.UNSUPPORTED, (
        "a host without /proc is unsupported, not failed: the distinction "
        "tells an operator the platform is at fault, not this process"
    )
    assert report.reason, "the report must say why the probe cannot run here"
