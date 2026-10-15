"""Contract tests for the process-scoped listening-socket probe.

``tests/installed_smoke.py`` asserts that a headless run binds no socket, and
that assertion is only worth anything if the probe underneath it can actually
see a socket. These tests are the probe's own negative controls: one proves it
detects a process that really is listening, and one proves it does not
attribute another process's listener to an idle one.

Without these, a probe that always returned an empty list would let the
headless check pass unconditionally — a green result that measured nothing.
"""

from __future__ import annotations

import dataclasses
import subprocess  # ruff: ignore[suspicious-subprocess-import]  # spawns fixed interpreter snippets; shell=False
import sys
import time
import typing as typ

if typ.TYPE_CHECKING:
    import collections.abc as cabc

import pytest
from listener_probe import is_probe_available, listening_ports

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

# Linux gates the probe, and /proc/1 is present on any Linux host.
_NEEDS_PROC = pytest.mark.skipif(
    not is_probe_available(1), reason="the listener probe needs a Linux /proc"
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


@_NEEDS_PROC
def test_probe_detects_a_real_listener(listening_child: _ListeningChild) -> None:
    """The probe must see a port that a process genuinely bound.

    This is the check that keeps the headless assertion honest: if the probe
    could not observe a listener, every "no listener" result would be vacuous.
    """
    assert listening_child.port in listening_ports(listening_child.process.pid), (
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
    idle = _spawn(_IDLE_CHILD)
    try:
        time.sleep(0.3)
        assert listening_child.port not in listening_ports(idle.pid), (
            "the probe attributed another process's listener to an idle process"
        )
    finally:
        _kill(idle)


def test_probe_is_available_is_false_for_a_process_without_proc(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unreadable process must be reported as unavailable, not as silent.

    The distinction is what stops "the check never ran" from being read as
    "the check found nothing" on a platform without ``/proc``.
    """
    monkeypatch.setattr("listener_probe.Path", lambda _path: _UnreadableProc())

    assert is_probe_available(1) is False, "an unreadable table is not available"
    assert not listening_ports(1), "an unreadable table yields no ports"


class _UnreadableProc:
    """A stand-in path whose existence and contents cannot be read."""

    def exists(self) -> bool:
        """Report the path as absent, as on a platform without ``/proc``."""
        return False

    def glob(self, _pattern: str) -> list[object]:
        """Report no descriptors, as an unreadable process directory would."""
        return []

    def read_text(self, *, encoding: str) -> str:
        """Fail to read, as an unreadable listing table would."""
        raise _UnreadableTableError(encoding)


class _UnreadableTableError(OSError):
    """Stand-in for a listing table that cannot be read on this platform."""

    def __init__(self, encoding: str) -> None:
        """Record which encoding the failed read used."""
        super().__init__("no such table", encoding, "unreadable /proc entry")
