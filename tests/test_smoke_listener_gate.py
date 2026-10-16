"""Contract tests for the smoke gate's use of the listening-socket probe.

``tests/test_listener_probe.py`` asks whether the probe *measures* correctly.
This module asks the separate question the headless certification depends on:
what the driver does with each answer. The gate may accept exactly one verdict —
``MEASURED`` with no ports — and every other outcome has to fail it, because a
gate that accepted an inconclusive probe would report a headless pass on a host
where it never looked at a socket.

The boundary is exercised directly rather than through the installed command.
That end-to-end path already runs in ``test_installed_commands.py``; what is not
covered there is *which* answer produces which verdict, which is a branch in
``installed_smoke`` and can be driven from a stub in a few milliseconds.
"""

from __future__ import annotations

import dataclasses

import installed_smoke
import pytest
from listener_probe import ListenerReport, ProbeOutcome


@dataclasses.dataclass(slots=True)
class _StubClient:
    """The two members ``_assert_no_listener`` reads from a smoke client.

    ``stderr_lines`` is held as a list and joined on read because that is what
    the real client does: it collects the child's output line by line as the
    process writes it, then joins. Storing the finished string instead would
    make this double's shape differ from the boundary it stands in for, and the
    failure messages under test quote what a partially-collected stream looks
    like.
    """

    process: _StubProcess
    stderr_lines: tuple[str, ...] = ()

    def stderr_text(self) -> str:
        """Return the child's standard error, joined as the real client joins it."""
        return "\n".join(self.stderr_lines)


@dataclasses.dataclass(slots=True)
class _StubProcess:
    """A process handle carrying only the pid the probe reads."""

    pid: int


def _run_boundary(
    monkeypatch: pytest.MonkeyPatch,
    report: ListenerReport,
) -> None:
    """Run the smoke boundary against ``report``, so its verdict is observable.

    The driver's real client starts an installed command, which this test does
    not need: the boundary only reads the child's pid and its standard error, so
    a stub supplies both and the branch under test is reached directly rather
    than through the end-to-end path that fails on any ``SmokeError``.

    ``probe_listeners`` is replaced outright, so ``listener_probe.PROC_ROOT`` is
    never consulted here and is deliberately not pointed at a temporary tree —
    doing so would suggest this test exercised the probe's own file reads, which
    ``tests/test_listener_probe_tables.py`` covers instead.
    """
    monkeypatch.setattr(installed_smoke, "probe_listeners", lambda _pid: report)
    client = _StubClient(_StubProcess(999999), stderr_lines=("child stderr",))
    # The private boundary is the unit under test here, not the driver around it.
    installed_smoke._assert_no_listener(client, "startup")


def test_smoke_boundary_fails_on_an_unsupported_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unsupported probe must fail the smoke gate, not pass quietly.

    A platform whose socket tables cannot be read cannot certify that the server
    bound nothing. Accepting it would make the gate green on a host where it
    never looked, which is the vacuous result the driver exists to prevent.
    """
    report = ListenerReport(ProbeOutcome.UNSUPPORTED, reason="no /proc on this host")

    with pytest.raises(installed_smoke.SmokeError, match="inconclusive"):
        _run_boundary(monkeypatch, report)


def test_smoke_boundary_fails_on_a_failed_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed probe must fail the smoke gate and name what went wrong.

    ``FAILED`` and ``UNSUPPORTED`` call for different operator responses, so the
    boundary must carry the report's own reason through rather than flattening
    both into one message.
    """
    report = ListenerReport(
        ProbeOutcome.FAILED, reason="PermissionError: [Errno 13] /proc/1/fd"
    )

    with pytest.raises(installed_smoke.SmokeError, match="PermissionError"):
        _run_boundary(monkeypatch, report)


def test_smoke_boundary_fails_when_a_socket_was_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A conclusive report naming a port must fail, and name the port.

    This is the one outcome the gate is written to catch, so it is asserted
    beside the inconclusive paths that must not be mistaken for it.
    """
    report = ListenerReport(ProbeOutcome.MEASURED, ports=(34567,))

    with pytest.raises(installed_smoke.SmokeError, match="34567"):
        _run_boundary(monkeypatch, report)


def test_smoke_boundary_certifies_only_a_measured_empty_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The sole passing verdict must be a conclusive empty measurement.

    Without this case the three failure tests above would also pass against a
    boundary that rejected everything, so the success path is what makes them
    evidence about the branch rather than about its absence.
    """
    report = ListenerReport(ProbeOutcome.MEASURED)

    _run_boundary(monkeypatch, report)  # must not raise
