"""Contract tests for the probe's reading of synthetic ``/proc`` tables.

The controls here point the probe at a ``/proc`` tree the test writes itself, so
the paths that need a misbehaving host — an unlistable descriptor directory, a
truncated row, an absent table, an address with no port — can be reached
deliberately rather than waiting for a real kernel to misbehave. Every one of
them asserts the same invariant: a table the probe cannot read becomes a
``FAILED`` report, never a ``MEASURED`` empty answer. Conflating the two is the
vacuous pass this module exists to prevent.

The live-process controls live in ``tests/test_listener_probe.py``, and the
driver's use of each answer in ``tests/test_smoke_listener_gate.py``.
"""

from __future__ import annotations

import contextlib
import tempfile
import typing as typ
from pathlib import Path

if typ.TYPE_CHECKING:
    import collections.abc as cabc

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from listener_probe import ListenerReport, ProbeOutcome, probe_listeners

_OWNS_INODE = 424242
_FOREIGN_INODE = 999999

# The properties below build a real /proc tree and read it back, so a per-example
# wall-clock deadline would time the temporary-directory setup rather than the
# probe. Each example is bounded by the generated input size instead.
_IO_BOUND = settings(deadline=None)


def _can_list(directory: Path) -> bool:
    """Report whether ``directory`` can be listed by this process."""
    try:
        list(directory.iterdir())
    except OSError:
        return False
    return True


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

    _assert_refused(report, "an unlistable descriptor table")


# Two rows a real kernel never writes, but a truncated read or a corrupt page
# could produce. They are separate cases because they fail in different places:
# the short row is rejected by the column count before any parse, while the
# full-length row reaches the address parse and is where a slice used to raise
# ``IndexError`` out of the probe.
_MALFORMED_ROWS = {
    "truncated-row": (
        "a listing row with no inode column",
        (
            "  sl  local_address rem_address   st\n"
            "   0: 0100007F:1F90 00000000:0000 0A 00000000:00000000\n"
        ),
    ),
    "address-without-port": (
        "an address field with no port separator",
        (
            "  sl  local_address rem_address   st tx_queue rx_queue tr tm->when "
            "retrnsmt   uid  timeout inode\n"
            "   0: 0100007F 00000000:0000 0A 00000000:00000000 00:00000000 "
            "00000000  1000        0 424242 1\n"
        ),
    ),
}


@pytest.mark.parametrize(
    ("what", "table"), _MALFORMED_ROWS.values(), ids=list(_MALFORMED_ROWS)
)
def test_probe_reports_a_malformed_row_as_failed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, what: str, table: str
) -> None:
    """An unreadable row must fail the probe, not be skipped or raise.

    Skipping it could drop a real listener and so turn a bound socket into a
    false negative — the precise error the headless check must not make — while
    letting a parse error escape would abort the smoke driver with a traceback
    instead of the ``FAILED`` verdict it knows how to report. Both rows are
    otherwise listening sockets owned by the pid, so each reaches the check it
    is meant to exercise rather than being filtered out earlier.
    """
    proc = _hand_built_proc(tmp_path / "proc", tcp=table, owns_inode=424242)
    monkeypatch.setattr("listener_probe.PROC_ROOT", proc)

    _assert_refused(probe_listeners(1), what, names="row")


def test_probe_reports_an_absent_ipv4_table_as_failed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A missing ``tcp`` table must fail the probe, not certify an empty answer.

    ``tcp6`` is genuinely optional, since a kernel can be built without IPv6.
    The IPv4 table is not: every kernel carries it. Treating its absence as "no
    listeners" let the probe answer ``MEASURED`` while having read no socket
    table at all, which is the vacuous pass this module exists to prevent.
    """
    # tcp is absent; a present-but-empty tcp6 must not stand in for it.
    proc = _hand_built_proc(tmp_path / "proc", tcp=None)
    (proc / "1" / "net" / "tcp6").write_text(
        "  sl  local_address rem_address   st\n", encoding="utf-8"
    )
    monkeypatch.setattr("listener_probe.PROC_ROOT", proc)

    _assert_refused(probe_listeners(1), "an absent IPv4 table")


def _assert_refused(
    report: ListenerReport, what: str, *, names: str | None = None
) -> None:
    """Assert ``report`` refused to answer rather than measuring an empty result.

    Every failure path in this module promises the same things: the outcome is
    ``FAILED`` rather than a measurement, no ports ride along with a non-answer,
    and the reason is populated so an operator has something to act on. That
    part is invariant, so it is asserted once here instead of restated at each
    call site; ``what`` names the condition in the failure message so a broken
    test still says which one it was.

    ``names`` adds a reason-substring check for the paths whose whole point is
    that the *row* was unreadable, as opposed to the table being absent.
    """
    assert report.outcome is ProbeOutcome.FAILED, (
        f"{what} must be a failed probe, not a measurement"
    )
    assert not report.ports, "a failed probe must not report ports"
    assert report.reason, f"the probe must say why {what} could not be read"
    if names is not None:
        assert names in report.reason or "Malformed" in report.reason, (
            f"the reason must name {names}, got: {report.reason!r}"
        )


def _table_text(rows: list[str]) -> str:
    """Render a ``/proc/net/tcp`` file from ``rows``, header included."""
    header = (
        "  sl  local_address rem_address   st tx_queue rx_queue tr tm->when "
        "retrnsmt   uid  timeout inode\n"
    )
    return header + "".join(f"{row}\n" for row in rows)


def _hand_built_proc(
    root: Path, *, tcp: str | None, owns_inode: int | None = None
) -> Path:
    """Lay out a ``/proc/<pid>`` for a test whose table text is written by hand.

    ``_write_proc`` serves the property tests, which build rows through
    ``_listing_row``. The example tests above need to spell a row out character
    by character — that is the point of them, since the defect is in the exact
    columns — so they pass the file text directly and use this to place it.

    ``owns_inode`` adds the descriptor symlink that makes ``pid`` the socket's
    owner, which the tests about a parse reaching the port need and the ones
    about a table read failing do not.
    """
    (root / "1" / "fd").mkdir(parents=True)
    if owns_inode is not None:
        (root / "1" / "fd" / "7").symlink_to(f"socket:[{owns_inode}]")
    (root / "1" / "net").mkdir(parents=True)
    if tcp is not None:
        (root / "1" / "net" / "tcp").write_text(tcp, encoding="utf-8")
    return root


def _listing_row(port: int, *, is_listening: bool, inode: int) -> str:
    """Render one ``/proc/net/tcp`` data row for ``port`` owned by ``inode``.

    The column positions are the real ones the probe's constants index, so a row
    built here is read by the same code path a real kernel's row takes.
    """
    fields = [
        "0:",
        f"0100007F:{port:04X}",
        "00000000:0000",
        "0A" if is_listening else "01",
        "00000000:00000000",
        "00:00000000",
        "00000000",
        "1000",
        "0",
        str(inode),
        "1",
    ]
    return " ".join(fields)


def _write_proc(
    root: Path, *, tcp: str | None, owned_inodes: set[int] = frozenset()
) -> None:
    """Lay out a synthetic ``/proc/<pid>`` holding the owned socket descriptors."""
    (root / "1" / "fd").mkdir(parents=True)
    for index, inode in enumerate(sorted(owned_inodes)):
        (root / "1" / "fd" / str(index)).symlink_to(f"socket:[{inode}]")
    (root / "1" / "net").mkdir()
    if tcp is not None:
        (root / "1" / "net" / "tcp").write_text(tcp, encoding="utf-8")


@contextlib.contextmanager
def _probe_at(
    tcp_text: str, owned_inodes: set[int] = frozenset()
) -> cabc.Iterator[None]:
    """Point the probe at a synthetic ``/proc`` for the duration of a block.

    A context manager rather than the ``monkeypatch`` fixture, because these are
    property tests: a function-scoped fixture is not reset between generated
    inputs, which is exactly the kind of stale-state bug a property test would
    otherwise report as a probe failure.
    """
    with tempfile.TemporaryDirectory() as scratch:
        proc = Path(scratch) / "proc"
        _write_proc(proc, tcp=tcp_text, owned_inodes=owned_inodes)
        with pytest.MonkeyPatch.context() as monkeypatch:
            monkeypatch.setattr("listener_probe.PROC_ROOT", proc)
            yield


@_IO_BOUND
@given(
    rows=st.lists(st.text(max_size=80), max_size=6),
    inodes=st.sets(st.integers(min_value=0, max_value=2**32), max_size=6),
)
def test_probe_never_raises_for_generated_tables(
    rows: list[str], inodes: set[int]
) -> None:
    """Arbitrary table text must always yield a report, never a traceback.

    A probe that raises out of ``probe_listeners`` aborts the smoke driver with
    an unhandled exception instead of the ``FAILED`` verdict the driver knows
    how to report. Slicing an address field for its port used to do exactly
    that, so the property is that no generated text can escape the report.
    """
    with _probe_at(_table_text(rows), owned_inodes=inodes):
        report = probe_listeners(1)

    assert report.outcome is not ProbeOutcome.UNSUPPORTED, (
        "a present /proc must never be reported as unsupported"
    )
    if report.outcome is ProbeOutcome.FAILED:
        assert report.reason, "a failed probe must say what it could not read"
        assert not report.ports, "a failed probe must not carry ports"


@_IO_BOUND
@given(
    entries=st.lists(
        st.tuples(
            st.integers(min_value=1, max_value=65535),
            st.booleans(),
            st.booleans(),
        ),
        max_size=6,
    )
)
def test_probe_reports_exactly_the_generated_listening_ports(
    entries: list[tuple[int, bool, bool]],
) -> None:
    """The reported ports must be exactly the owned listening rows, no others.

    This is the property that makes ``MEASURED`` mean something: the answer is
    the set derived from the table, so an owned listener is never dropped and a
    foreign or non-listening socket is never claimed. Ports are compared as a
    set because a table lists a port once per socket, and the probe reports each
    listening socket it attributes.
    """
    rows: list[str] = []
    expected: set[int] = set()
    for port, is_listening, is_owned in entries:
        rows.append(
            _listing_row(
                port,
                is_listening=is_listening,
                inode=_OWNS_INODE if is_owned else _FOREIGN_INODE,
            )
        )
        if is_listening and is_owned:
            expected.add(port)

    with _probe_at(_table_text(rows), owned_inodes={_OWNS_INODE}):
        report = probe_listeners(1)

    assert report.outcome is ProbeOutcome.MEASURED, (
        f"well-formed rows must allow a conclusive answer, got: {report.reason!r}"
    )
    assert set(report.ports) == expected, (
        f"the probe must report exactly the owned listening ports; "
        f"expected {sorted(expected)}, got {sorted(report.ports)}"
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
