"""Contract tests for the process-scoped listening-socket probe.

``tests/installed_smoke.py`` asserts that a headless run binds no socket, and
that assertion is only worth anything if the probe underneath it can actually
see a socket. These tests are the probe's own controls: they prove it detects a
process that really is listening, that it does not attribute another process's
listener to an idle one, and that it reports an unreadable table as
inconclusive rather than as an empty result.

Without the last group, a probe that returned "no listener" whenever it failed
to read ``/proc`` would let the headless check pass unconditionally — a green
result that measured nothing.
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


def test_probe_reports_an_unlistable_descriptor_table_as_failed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A descriptor table that cannot be listed must not read as "no socket".

    ``Path.glob`` swallows the ``OSError`` for a directory it cannot list and
    yields nothing, which is exactly how an unreadable table used to become a
    vacuous pass. The probe reads the directory with ``iterdir`` so the failure
    reaches the caller; this test is the control for that choice.
    """
    proc = tmp_path / "proc"
    (proc / "1" / "net").mkdir(parents=True)
    (proc / "1" / "net" / "tcp").write_text("  sl local_address rem_address st\n")
    # The fd directory exists but carries no read permission, as another user's
    # process does on a real host.
    (proc / "1" / "fd").mkdir()
    (proc / "1" / "fd").chmod(0o000)
    monkeypatch.setattr("listener_probe.PROC_ROOT", proc)
    try:
        if _can_list(proc / "1" / "fd"):
            pytest.skip("this test needs to be able to detect an unlistable directory")

        report = probe_listeners(1)
    finally:
        (proc / "1" / "fd").chmod(0o700)

    assert report.outcome is ProbeOutcome.FAILED, (
        "an unlistable descriptor table is a failed probe, not an empty result"
    )
    assert not report.ports, "silence must never be reported as a measurement"


def _can_list(directory: Path) -> bool:
    """Report whether ``directory`` can be listed by this process."""
    try:
        list(directory.iterdir())
    except OSError:
        return False
    return True


def test_probe_reports_a_malformed_table_as_failed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A listing row with no inode column must fail the probe, not be skipped.

    Skipping the row could drop a real listener and so turn a bound socket into
    a false negative — the precise error the headless check must not make.
    """
    proc = tmp_path / "proc"
    (proc / "1" / "fd").mkdir(parents=True)
    socket_link = proc / "1" / "fd" / "7"
    socket_link.symlink_to("socket:[424242]")
    (proc / "1" / "net").mkdir()
    (proc / "1" / "net" / "tcp").write_text(
        "  sl  local_address rem_address   st\n"
        "   0: 0100007F:1F90 00000000:0000 0A 00000000:00000000\n"
    )
    monkeypatch.setattr("listener_probe.PROC_ROOT", proc)

    report = probe_listeners(1)

    assert report.outcome is ProbeOutcome.FAILED, (
        "a truncated row must not be silently ignored"
    )
    assert "Malformed" in report.reason or "row" in report.reason, (
        f"the reason must name the malformed row, got: {report.reason!r}"
    )


def test_probe_refuses_an_unrecognized_outcome() -> None:
    """The driver must fail closed on an outcome it does not recognise.

    ``_assert_no_listener`` treats only ``MEASURED`` as certification and raises
    for everything else, so a future outcome cannot silently become a pass. The
    enum's members are pinned here so that adding one is a reviewed decision
    rather than an accident.
    """
    assert {outcome.name for outcome in ProbeOutcome} == {
        "MEASURED",
        "UNSUPPORTED",
        "FAILED",
    }, "a new outcome needs a driver decision before it is added"
