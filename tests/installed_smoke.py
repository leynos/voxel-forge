"""Drive the *installed* ``voxel-forge-mcp`` through a real headless session.

Roadmap step 1.3.2 asks the readiness workflow to cover the headless server
start and a scene export. ``voxel-forge-mcp --help`` cannot satisfy that: it
exits inside ``argparse`` and never reaches the server loop, so it proves the
console script is on the ``PATH`` and nothing more. A check that imports
``voxel_forge`` from the checkout has the same gap in a subtler form — it can
pass while the installed distribution is broken.

This module therefore speaks the protocol the way a client does. It launches
the console script resolved from the ``PATH``, performs the MCP ``initialize``
handshake over stdio, calls the scene tools, and asserts that the process
bound no listening socket at any point. It imports only the standard library,
and never imports ``voxel_forge``, so the interpreter running it cannot
silently supply the package from the source tree.

Run it directly, or through the ``installed_smoke`` pytest wrapper:

.. code-block:: console

    $ python tests/installed_smoke.py
    installed smoke OK: ... -> /tmp/....vox (N bytes), no listening socket
"""

from __future__ import annotations

import json
import os
import queue
import shutil
import signal
import subprocess  # ruff: ignore[suspicious-subprocess-import]  # launches the installed command with fixed args; shell=False
import sys
import tempfile
import threading
import time
import typing as typ
from pathlib import Path

if typ.TYPE_CHECKING:
    import collections.abc as cabc

from listener_probe import ProbeOutcome, probe_listeners

COMMAND_NAME = "voxel-forge-mcp"
PROTOCOL_VERSION = "2025-11-25"
STARTUP_ANNOUNCEMENT = "operation=server_start"
STARTUP_TIMEOUT_SECONDS = 30.0
CALL_TIMEOUT_SECONDS = 60.0
SHUTDOWN_TIMEOUT_SECONDS = 10.0

_EXPECTED_TOOL_CALLS = (
    ("voxelforge_create_scene", {"name": "ci_smoke"}),
    (
        "voxelforge_fill_box",
        {"x1": 0, "x2": 3, "y1": 0, "y2": 1, "z1": 0, "z2": 2, "color": "2"},
    ),
)


class SmokeError(RuntimeError):
    """A headless contract the installed command failed to meet."""


class _StdioClient:
    """A minimal newline-delimited JSON-RPC client for a child process."""

    def __init__(self, command: str, environment: dict[str, str]) -> None:
        """Start ``command`` and begin reading its protocol streams.

        The process is held open for the lifetime of the client and reaped by
        :meth:`close`, which has to escalate to a kill when the server ignores
        a polite termination. A ``with`` block cannot express that shutdown
        sequence, so the handle is deliberately stored rather than scoped to
        this method.
        """
        self._next_id = 0
        self._responses: dict[int, dict[str, object]] = {}
        self._notifications: queue.Queue[str] = queue.Queue()
        self._stderr: list[str] = []
        # pylint: disable-next=consider-using-with  # reaped by close(), which may escalate to a kill
        self.process = subprocess.Popen(  # ruff: ignore[subprocess-without-shell-equals-true]  # resolved absolute path, fixed argv, shell=False
            [command],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=environment,
        )
        stdout = self.process.stdout
        stderr = self.process.stderr
        assert stdout is not None, "stdout is a pipe, as requested"
        assert stderr is not None, "stderr is a pipe, as requested"
        self._readers = [
            threading.Thread(
                target=self._collect, args=(stdout, self._ingest), daemon=True
            ),
            threading.Thread(
                target=self._collect, args=(stderr, self._stderr.append), daemon=True
            ),
        ]
        for reader in self._readers:
            reader.start()

    @staticmethod
    def _collect(stream: typ.IO[str], sink: cabc.Callable[[str], None]) -> None:
        """Forward each line of ``stream`` to ``sink`` until it closes."""
        try:
            for line in stream:
                sink(line.rstrip("\n"))
        except ValueError:
            # The pipe closed under us during shutdown; the process is gone,
            # and a reader thread has nothing left to do.
            pass

    def _ingest(self, line: str) -> None:
        """Record a protocol line or a human-readable one."""
        if not line:
            return
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            self._notifications.put(line)
            return
        identifier = message.get("id")
        if isinstance(identifier, int):
            self._responses[identifier] = message
        else:
            self._notifications.put(line)

    def stderr_text(self) -> str:
        """Return everything the child has written to standard error so far."""
        return "\n".join(self._stderr)

    def _raise_if_exited(self, awaiting: str) -> None:
        """Fail a wait when the child has already exited without satisfying it.

        Both waits below would otherwise spin until their timeout and report a
        deadline, which buries the real cause: a server that died. Naming what
        was being awaited keeps the diagnosis specific to the failed step.
        """
        if self.process.poll() is None:
            return
        msg = (
            f"the server exited while awaiting {awaiting} with status "
            f"{self.process.returncode}:\n{self.stderr_text()}"
        )
        raise SmokeError(msg)

    def await_announcement(self, timeout: float) -> str:
        """Block until the startup announcement appears, and return it."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for line in self.stderr_text().splitlines():
                if STARTUP_ANNOUNCEMENT in line:
                    return line
            self._raise_if_exited("the startup announcement")
            time.sleep(0.05)
        msg = (
            f"no startup announcement within {timeout}s; stderr was:\n"
            f"{self.stderr_text()}"
        )
        raise SmokeError(msg)

    def call(
        self, method: str, params: dict[str, object], timeout: float
    ) -> dict[str, object]:
        """Send a request and return its result, raising on a protocol error."""
        self._next_id += 1
        identifier = self._next_id
        request = {
            "jsonrpc": "2.0",
            "id": identifier,
            "method": method,
            "params": params,
        }
        assert self.process.stdin is not None, "stdin is a pipe by construction"
        self.process.stdin.write(json.dumps(request) + "\n")
        self.process.stdin.flush()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if identifier in self._responses:
                message = self._responses.pop(identifier)
                if "error" in message:
                    msg = f"{method} failed: {message['error']}"
                    raise SmokeError(msg)
                result = message.get("result")
                assert isinstance(result, dict), f"{method} returned no result object"
                return result
            self._raise_if_exited(f"a response to {method}")
            time.sleep(0.05)
        msg = f"{method} produced no response within {timeout}s"
        raise SmokeError(msg)

    def notify(self, method: str) -> None:
        """Send a notification, which by definition expects no response."""
        assert self.process.stdin is not None, "stdin is a pipe by construction"
        self.process.stdin.write(
            json.dumps({"jsonrpc": "2.0", "method": method}) + "\n"
        )
        self.process.stdin.flush()

    def close(self) -> None:
        """Terminate the child and reap it, even if it ignores a polite close."""
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(SHUTDOWN_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                self.process.send_signal(signal.SIGKILL)
                self.process.wait(SHUTDOWN_TIMEOUT_SECONDS)
        for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
            if stream is not None:
                stream.close()


def resolve_command(explicit: str | None = None) -> str:
    """Find the installed console script, refusing anything else.

    When ``explicit`` names a path it must exist and be a file; otherwise the
    command is resolved from the ``PATH``. Both routes fail loudly rather than
    falling back to an in-tree import, because a check that quietly exercises
    the checkout instead of the installed artifact is the defect this module
    exists to catch.
    """
    if explicit is not None:
        candidate = Path(explicit)
        if not candidate.is_file():
            msg = f"the requested command {explicit!r} does not exist"
            raise SmokeError(msg)
        return str(candidate)
    resolved = shutil.which(COMMAND_NAME)
    if resolved is None:
        msg = (
            f"{COMMAND_NAME} is not on the PATH, so no installed command was "
            "exercised; install it with `uv tool install .` before running"
        )
        raise SmokeError(msg)
    return resolved


def _child_environment() -> dict[str, str]:
    """Build an environment in which only the installed package is importable.

    ``PYTHONPATH`` and ``PYTHONHOME`` are removed because they take precedence
    over the installed distribution: with the repository's ``src`` directory on
    ``PYTHONPATH`` the console script imports the checkout, and this check
    would pass without the installed artifact ever loading. ``VOXELFORGE_BRIDGE``
    is removed so an ambient setting cannot supply the bridge the test exists
    to rule out, and ``PYTHONNOUSERSITE`` keeps a user site directory from
    shadowing the installed package.
    """
    environment = {
        key: value
        for key, value in os.environ.items()
        if key not in {"PYTHONPATH", "PYTHONHOME", "VOXELFORGE_BRIDGE"}
    }
    environment["PYTHONNOUSERSITE"] = "1"
    return environment


def _tool_text(result: dict[str, object]) -> str:
    """Extract the single text payload a VoxelForge tool returns."""
    content = result.get("content")
    if not isinstance(content, list) or not content:
        msg = f"a tool call must return content, got: {result}"
        raise SmokeError(msg)
    first = content[0]
    if not isinstance(first, dict):
        msg = f"a tool result must be an object, got: {first!r}"
        raise SmokeError(msg)
    text = first.get("text")
    if not isinstance(text, str):
        msg = f"a VoxelForge tool must return one text payload, got: {first!r}"
        raise SmokeError(msg)
    return text


def _assert_no_listener(client: _StdioClient, stage: str) -> None:
    """Fail if the child is listening, or if the check could not be conclusive.

    An inconclusive probe is a failure rather than a quiet pass. The whole point
    of this driver is to certify that the server bound nothing, and a platform
    where the socket tables cannot be read cannot certify that — reporting OK
    anyway would be the vacuous green result this module exists to prevent.

    Examples
    --------
    >>> _assert_no_listener(client, "startup")  # raises unless nothing is bound
    """
    report = probe_listeners(client.process.pid)
    if report.outcome is ProbeOutcome.MEASURED:
        if report.ports:
            msg = (
                f"the server bound port(s) {list(report.ports)} during {stage}, "
                f"but a headless run must bind none:\n{client.stderr_text()}"
            )
            raise SmokeError(msg)
        return
    msg = (
        f"the listening-socket check was inconclusive during {stage} "
        f"({report.outcome.value}): {report.reason}\n"
        "a headless run cannot be certified without it"
    )
    raise SmokeError(msg)


def run_smoke(export_path: Path, command_path: str | None = None) -> str:
    """Run one headless session against the installed command.

    Returns a human-readable summary, or raises :class:`SmokeError`.

    The session asserts the two halves of the 1.3 contract together: the
    server completes real work over stdio, and it never opens a listening
    socket while doing so. ``--bridge`` is deliberately not passed, and
    ``VOXELFORGE_BRIDGE`` is removed from the child environment so an ambient
    setting cannot supply the bridge this test exists to rule out.
    """
    command = resolve_command(command_path)
    environment = _child_environment()

    client = _StdioClient(command, environment)
    try:
        announcement = client.await_announcement(STARTUP_TIMEOUT_SECONDS)
        if "bridge_mode=headless" not in announcement:
            msg = f"a default run must report headless mode, got: {announcement}"
            raise SmokeError(msg)
        if "bridge_state=down" not in announcement:
            msg = f"a default run must start with the bridge down, got: {announcement}"
            raise SmokeError(msg)

        _assert_no_listener(client, "startup")

        client.call(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "voxel-forge-ci-smoke", "version": "1.0"},
            },
            CALL_TIMEOUT_SECONDS,
        )
        client.notify("notifications/initialized")

        for name, arguments in _EXPECTED_TOOL_CALLS:
            _tool_text(
                client.call(
                    "tools/call",
                    {"name": name, "arguments": arguments},
                    CALL_TIMEOUT_SECONDS,
                )
            )

        exported = _tool_text(
            client.call(
                "tools/call",
                {
                    "name": "voxelforge_export_vox",
                    "arguments": {"output_path": str(export_path)},
                },
                CALL_TIMEOUT_SECONDS,
            )
        )
        if not export_path.is_file() or export_path.stat().st_size == 0:
            msg = f"the export produced no bytes:\n{exported}"
            raise SmokeError(msg)

        _assert_no_listener(client, "the whole session")
    finally:
        client.close()

    size = export_path.stat().st_size
    return (
        f"installed smoke OK: {command} -> {export_path} ({size} bytes), "
        "no listening socket"
    )


def main() -> int:
    """Run the smoke session, printing a summary or a diagnosed failure."""
    with tempfile.TemporaryDirectory() as workspace:
        export_path = Path(workspace) / "ci_smoke.vox"
        try:
            summary = run_smoke(export_path)
        except SmokeError as failure:
            print(f"installed smoke FAILED: {failure}", file=sys.stderr)
            return 1
    print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
