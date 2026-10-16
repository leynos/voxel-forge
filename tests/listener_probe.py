"""Attribute listening TCP sockets to one process, using only the standard library.

The headless contract in roadmap step 1.3 is about a *particular* process: the
``voxel-forge-mcp`` run under test must not hold a listening socket. ``ss`` and
``lsof`` report the whole host, so on a shared or busy machine they would also
see an unrelated server and could not say whether this process bound anything.
Reading the process's own file descriptors and intersecting them with its
network namespace's listening table attributes a socket to that process alone.

A query answers with a :class:`ListenerReport` rather than a bare list of ports,
because an empty list is ambiguous: it means both "this process holds no
listening socket" and "the tables could not be read". Conflating the second with
the first would let the headless check pass without measuring anything, which is
the one failure this module exists to prevent. Callers therefore have to say
what they intend to do about an inconclusive answer.

The probe is deliberately separate from the MCP session driver so the socket
attribution can be exercised on its own, including against a process that
really is listening.
"""

from __future__ import annotations

import dataclasses
import enum
from pathlib import Path

# st == 0A is TCP_LISTEN in /proc/net/tcp's state column.
_TCP_LISTEN = "0A"
_SOCKET_PREFIX = "socket:["

# Column positions in a listing row: 1 is the local address and port (the port
# is hexadecimal), 3 is the connection state, and 9 is the socket inode.
_LOCAL_ADDRESS_FIELD = 1
_STATE_FIELD = 3
_INODE_FIELD = 9

# Module-level rather than inlined so a test can point the probe at a synthetic
# tree and exercise the failure paths without an unreadable real /proc.
PROC_ROOT = Path("/proc")


class ProbeOutcome(enum.Enum):
    """What one listener query managed to establish about a process."""

    MEASURED = "measured"
    """The tables were readable, so ``ports`` is the complete answer."""

    UNSUPPORTED = "unsupported"
    """This host has no ``/proc``, so the probe cannot run here at all."""

    FAILED = "failed"
    """``/proc`` is present, but this process could not be read."""


@dataclasses.dataclass(frozen=True, slots=True)
class ListenerReport:
    """A process's listening ports, and how conclusive that answer is.

    ``ports`` is only the complete answer when ``outcome`` is
    :attr:`ProbeOutcome.MEASURED`. The other outcomes carry no ports, and
    ``reason`` names what could not be read so an operator can tell a platform
    without ``/proc`` from a table that refused to be read.
    """

    outcome: ProbeOutcome
    ports: tuple[int, ...] = ()
    reason: str = ""


class _MalformedTableError(ValueError):
    """A listing row that cannot be attributed to any process."""


def _socket_inodes(pid: int) -> set[int]:
    """Return the socket inodes ``pid`` currently holds open.

    ``iterdir`` is used rather than ``glob`` deliberately. ``glob`` swallows the
    ``OSError`` raised by a directory it cannot list and yields nothing, which
    is indistinguishable from a process that holds no sockets; the error has to
    reach the caller so an inconclusive probe is reported as inconclusive.
    """
    inodes: set[int] = set()
    for descriptor in (PROC_ROOT / str(pid) / "fd").iterdir():
        try:
            target = str(descriptor.readlink())
        except OSError:
            # This one descriptor closed between the listing and the read. The
            # rest of the table is still readable, so carry on.
            continue
        if target.startswith(_SOCKET_PREFIX):
            inodes.add(int(target[len(_SOCKET_PREFIX) : -1]))
    return inodes


def _listening_ports(pid: int, inodes: set[int]) -> list[int]:
    """Return the listening ports ``pid`` holds, read from its network tables.

    Raises
    ------
    _MalformedTableError
        If a row is too short to carry an inode. Skipping such a row could hide
        a real listener and turn the answer into a false negative, so the probe
        refuses to answer rather than guessing.
    """
    ports: list[int] = []
    for name in ("tcp", "tcp6"):
        table = PROC_ROOT / str(pid) / "net" / name
        try:
            rows = table.read_text(encoding="utf-8")
        except FileNotFoundError:
            # A kernel built without IPv6 has no tcp6 table, and that is not a
            # read failure.
            continue
        for row in rows.splitlines()[1:]:
            fields = row.split()
            if not fields:
                continue
            if len(fields) <= _INODE_FIELD:
                msg = f"{table} held a row with no inode column: {row!r}"
                raise _MalformedTableError(msg)
            if (
                fields[_STATE_FIELD] == _TCP_LISTEN
                and int(fields[_INODE_FIELD]) in inodes
            ):
                ports.append(int(fields[_LOCAL_ADDRESS_FIELD].rsplit(":", 1)[1], 16))
    return ports


def _describe(failure: BaseException) -> str:
    """Name a probe failure, so a report can say what went wrong."""
    return f"{type(failure).__name__}: {failure}"


def probe_listeners(pid: int) -> ListenerReport:
    """Report the TCP ports ``pid`` listens on, or why that is unknown.

    The descriptor table and the network tables are read in this one call, so a
    caller cannot pair an availability answer from one moment with a reading
    taken at another.

    Examples
    --------
    >>> report = probe_listeners(999999)
    >>> report.outcome is ProbeOutcome.MEASURED
    False
    >>> bool(report.reason)
    True
    """
    if not PROC_ROOT.is_dir():
        return ListenerReport(ProbeOutcome.UNSUPPORTED, reason="no /proc on this host")
    try:
        ports = _listening_ports(pid, _socket_inodes(pid))
    except (OSError, ValueError) as failure:
        return ListenerReport(ProbeOutcome.FAILED, reason=_describe(failure))
    return ListenerReport(ProbeOutcome.MEASURED, tuple(ports))
