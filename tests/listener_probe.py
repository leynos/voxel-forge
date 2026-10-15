"""Attribute listening TCP sockets to one process, using only the standard library.

The headless contract in roadmap step 1.3 is about a *particular* process: the
``voxel-forge-mcp`` run under test must not hold a listening socket. ``ss`` and
``lsof`` report the whole host, so on a shared or busy machine they would also
see an unrelated server and could not say whether this process bound anything.
Reading the process's own file descriptors and intersecting them with its
network namespace's listening table attributes a socket to that process alone.

The probe is deliberately separate from the MCP session driver so the socket
attribution can be exercised on its own, including against a process that
really is listening.
"""

from __future__ import annotations

from pathlib import Path

# st == 0A is TCP_LISTEN in /proc/net/tcp's state column.
_TCP_LISTEN = "0A"
_SOCKET_PREFIX = "socket:["


def is_probe_available(pid: int) -> bool:
    """Report whether the listener table for ``pid`` can be read here.

    ``/proc`` is Linux-specific. A caller on another platform must be able to
    tell "no listener found" from "this check never ran", so that silence is
    not mistaken for proof.
    """
    return Path(f"/proc/{pid}/net/tcp").exists()


def _socket_inodes(pid: int) -> set[int]:
    """Return the socket inodes this process currently holds open."""
    inodes: set[int] = set()
    for descriptor in Path(f"/proc/{pid}/fd").glob("*"):
        try:
            target = str(descriptor.readlink())
        except OSError:
            # The descriptor can close between the glob and the read.
            continue
        if target.startswith(_SOCKET_PREFIX):
            inodes.add(int(target[len(_SOCKET_PREFIX) : -1]))
    return inodes


def listening_ports(pid: int) -> list[int]:
    """Return the TCP ports ``pid`` is listening on, and no other process's.

    Returns an empty list when the process holds no listening socket, and also
    when ``/proc`` is unavailable; call :func:`is_probe_available` first when
    the distinction matters.
    """
    inodes = _socket_inodes(pid)
    ports: list[int] = []
    for table in ("tcp", "tcp6"):
        try:
            rows = Path(f"/proc/{pid}/net/{table}").read_text(encoding="utf-8")
        except OSError:
            continue
        for row in rows.splitlines()[1:]:
            fields = row.split()
            # Field 1 is the local address:port (port in hex); field 9 the inode.
            if fields[3] == _TCP_LISTEN and int(fields[9]) in inodes:
                ports.append(int(fields[1].rsplit(":", 1)[1], 16))
    return ports
