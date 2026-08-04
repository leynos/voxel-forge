"""Supervise the Bun-hosted web editor process.

This module owns the lifecycle of the editor: it spawns Bun with explicit
arguments and no shell, reads stdout on a background thread so the pipe
cannot deadlock, waits for the structured ``listening`` event that carries
the bound port, and stops the child with a bounded timeout that escalates
from terminate to kill. It follows simulacat's ``orchestration`` module.

Examples
--------
Start and stop an editor::

    from voxel_forge.orchestration import (
        EditorPorts,
        start_editor_process,
        stop_editor_process,
    )

    ports = EditorPorts(bridge_ws=8765, bridge_http=8766)
    process, port = start_editor_process(ports)
    # The editor is now at http://127.0.0.1:{port}
    stop_editor_process(process)
"""

from __future__ import annotations

import atexit
import contextlib
import dataclasses as dc
import json
import os
import queue
import subprocess  # ruff: ignore[suspicious-subprocess-import]  # spawn Bun with validated arguments; shell=False
import sys
import threading
import time
import typing as typ

if typ.TYPE_CHECKING:
    from pathlib import Path

from voxel_forge.editor_runtime import (
    EditorRuntimeError,
    editor_entrypoint,
    editor_package_root,
)

DEFAULT_STOP_TIMEOUT_SECONDS = 5.0
DEFAULT_STARTUP_TIMEOUT_SECONDS = 30.0
_POLL_JOIN_TIMEOUT_SECONDS = 0.1


@dc.dataclass(frozen=True)
class EditorPorts:
    """Ports the editor needs to know about when it starts.

    ``requested`` is the port the editor should try to bind; ``0`` asks
    the operating system for an ephemeral one.
    """

    bridge_ws: int
    bridge_http: int
    requested: int = 0


def _spawn_editor(bun_executable: str, ports: EditorPorts) -> subprocess.Popen[str]:
    """Spawn the Bun editor process with an explicit environment."""
    env = dict(os.environ)
    env["VOXELFORGE_EDITOR_PORT"] = str(ports.requested)
    env["VOXELFORGE_BRIDGE_WS_PORT"] = str(ports.bridge_ws)
    env["VOXELFORGE_BRIDGE_HTTP_PORT"] = str(ports.bridge_http)
    try:
        return subprocess.Popen(  # ruff: ignore[subprocess-without-shell-equals-true]  # validated executable and script path; shell=False
            [bun_executable, str(editor_entrypoint())],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
            cwd=editor_package_root(),
        )
    except FileNotFoundError as exc:
        msg = f"Bun executable not found: {bun_executable}"
        raise EditorRuntimeError(msg) from exc


def _start_stdout_reader(
    process: subprocess.Popen[str],
) -> tuple[queue.Queue[str | None], threading.Thread]:
    """Feed the child's stdout into a queue from a background thread.

    A dedicated reader keeps the pipe drained, so the child can never
    block on a full stdout buffer while the parent waits elsewhere.
    """
    stdout = process.stdout
    if stdout is None:
        msg = "Failed to capture editor stdout"
        raise EditorRuntimeError(msg)

    line_queue: queue.Queue[str | None] = queue.Queue()

    def _reader() -> None:
        """Pump lines into the queue, ending with a sentinel at EOF."""
        for line in iter(stdout.readline, ""):
            line_queue.put(line)
        line_queue.put(None)

    thread = threading.Thread(target=_reader, name="editor-stdout-reader", daemon=True)
    thread.start()
    return line_queue, thread


def _parse_listening_port(line: str) -> int | None:
    """Extract the port from a ``listening`` event line, if it is one."""
    with contextlib.suppress(json.JSONDecodeError):
        event = json.loads(line)
        if isinstance(event, dict) and event.get("event") == "listening":
            try:
                return int(event["port"])
            except (KeyError, TypeError, ValueError) as exc:
                msg = f"Invalid listening event from editor: {event!r}"
                raise EditorRuntimeError(msg) from exc
    return None


def _next_line(line_queue: queue.Queue[str | None], deadline: float) -> str | None:
    """Take the next stdout line without blocking past the deadline."""
    remaining = max(0.0, deadline - time.monotonic())
    try:
        return line_queue.get(timeout=remaining)
    except queue.Empty:
        return None


def _wait_for_port(process: subprocess.Popen[str], startup_timeout: float) -> int:
    """Wait for the editor to report its listening port on stdout."""
    output_lines: list[str] = []
    deadline = time.monotonic() + startup_timeout
    line_queue, reader = _start_stdout_reader(process)

    try:
        while time.monotonic() < deadline:
            line = _next_line(line_queue, deadline)
            if line is None:
                if process.poll() is not None:
                    break
                continue
            output_lines.append(line)
            port = _parse_listening_port(line)
            if port is not None:
                return port
    finally:
        reader.join(timeout=_POLL_JOIN_TIMEOUT_SECONDS)

    stop_editor_process(process, timeout=1.0)
    msg = (
        "Editor did not report a listening port.\n"
        f"Exit code: {process.poll()}\n"
        f"Output:\n{''.join(output_lines)}"
    )
    raise EditorRuntimeError(msg)


def start_editor_process(
    ports: EditorPorts,
    *,
    bun_executable: str | None = None,
    startup_timeout: float = DEFAULT_STARTUP_TIMEOUT_SECONDS,
) -> tuple[subprocess.Popen[str], int]:
    """Start the editor and wait for it to report a listening port.

    Parameters
    ----------
    ports : EditorPorts
        Bridge endpoints to advertise to the page, and the requested
        editor port (``0`` for an ephemeral one).
    bun_executable : str | None
        Path or name of the Bun executable. Defaults to the ``BUN``
        environment variable or ``"bun"``.
    startup_timeout : float
        Maximum seconds to wait for the ``listening`` event.

    Returns
    -------
    tuple[subprocess.Popen[str], int]
        The process handle and the port the editor actually bound.

    Raises
    ------
    EditorRuntimeError
        If the editor cannot be spawned or reports no port in time.

    Examples
    --------
    >>> process, port = start_editor_process(  # doctest: +SKIP
    ...     EditorPorts(bridge_ws=8765, bridge_http=8766)
    ... )
    """
    executable = bun_executable or os.environ.get("BUN", "bun")
    entrypoint = editor_entrypoint()
    if not entrypoint.is_file():
        msg = f"Editor entry point not found: {entrypoint}"
        raise EditorRuntimeError(msg)

    process = _spawn_editor(executable, ports)
    port = _wait_for_port(process, startup_timeout)
    return process, port


def stop_editor_process(
    process: subprocess.Popen[str],
    *,
    timeout: float = DEFAULT_STOP_TIMEOUT_SECONDS,
) -> None:
    """Stop the editor, escalating from terminate to kill.

    Parameters
    ----------
    process : subprocess.Popen[str]
        The editor process to stop. Stopping an already-dead process is
        harmless.
    timeout : float
        Seconds to wait after ``terminate()`` and again after ``kill()``.

    Examples
    --------
    >>> stop_editor_process(process)  # doctest: +SKIP
    """
    with contextlib.suppress(OSError):
        process.terminate()
    with contextlib.suppress(subprocess.TimeoutExpired, OSError):
        process.wait(timeout=timeout)
    if process.poll() is None:
        with contextlib.suppress(OSError):
            process.kill()
        with contextlib.suppress(subprocess.TimeoutExpired, OSError):
            process.wait(timeout=timeout)


_supervised: dict[int, subprocess.Popen[str]] = {}
_supervised_lock = threading.Lock()


def supervise(process: subprocess.Popen[str]) -> None:
    """Register a process for reaping when the interpreter exits."""
    with _supervised_lock:
        _supervised[process.pid] = process


def reap_supervised() -> None:
    """Stop every registered process; called from ``atexit``."""
    with _supervised_lock:
        processes = list(_supervised.values())
        _supervised.clear()
    for process in processes:
        stop_editor_process(process)


atexit.register(reap_supervised)

_INSTALL_TIMEOUT_SECONDS = 300


def _decode_stream(stream: str | bytes | None) -> str:
    """Return a captured stream as text, whatever the caller received.

    ``TimeoutExpired`` carries whatever had been read when the deadline
    passed, and it can hold bytes even when the run requested text, so
    the type has to be checked rather than assumed.
    """
    if stream is None:
        return ""
    if isinstance(stream, bytes):
        return stream.decode("utf-8", errors="replace")
    return stream


def _relay_to_stderr(stdout: str | bytes | None, stderr: str | bytes | None) -> str:
    """Write both captured streams to stderr and return them joined.

    Bun's output must never reach this process's stdout: the install can
    run inside the MCP server, whose stdout carries the stdio protocol.
    """
    parts = [text for text in map(_decode_stream, (stdout, stderr)) if text]
    for text in parts:
        sys.stderr.write(text)
    return "".join(parts).strip()


def install_editor_dependencies(*, bun_executable: str | None = None) -> Path:
    """Install the bundled editor's JavaScript dependencies via Bun.

    Parameters
    ----------
    bun_executable : str | None
        Executable name or path for Bun. Defaults to the ``BUN``
        environment variable or ``"bun"``.

    Returns
    -------
    Path
        The resolved directory containing the editor's ``package.json``.

    Raises
    ------
    EditorRuntimeError
        If the package root cannot be resolved, Bun cannot be executed,
        or dependency installation fails or times out.

    Notes
    -----
    Bun's output is captured and relayed to stderr. The install may run
    inside the MCP server process, whose stdout carries the stdio
    protocol: an inherited stdout would let Bun's progress lines corrupt
    the channel for the connected client.

    Whatever Bun had produced before a timeout is relayed and appended to
    the error as well, since a hung install is precisely the case where
    its last few lines say why.

    Examples
    --------
    >>> install_editor_dependencies()  # doctest: +SKIP
    PosixPath('.../voxel_forge/editor')
    """
    executable = bun_executable or os.environ.get("BUN", "bun")
    package_root = editor_package_root()
    command = [executable, "install", "--cwd", str(package_root)]
    try:
        result = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true]  # explicit command list; shell=False
            command,
            check=False,
            timeout=_INSTALL_TIMEOUT_SECONDS,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        msg = f"Bun executable not found: {executable}"
        raise EditorRuntimeError(msg) from exc
    except subprocess.TimeoutExpired as exc:
        partial = _relay_to_stderr(exc.stdout, exc.stderr)
        msg = (
            "Timed out installing editor dependencies after "
            f"{_INSTALL_TIMEOUT_SECONDS}s with command: {' '.join(command)}"
        )
        if partial:
            msg = f"{msg}\n{partial}"
        raise EditorRuntimeError(msg) from exc
    detail = _relay_to_stderr(result.stdout, result.stderr)
    if result.returncode != 0:
        msg = f"Failed to install editor dependencies with command: {' '.join(command)}"
        if detail:
            msg = f"{msg}\n{detail}"
        raise EditorRuntimeError(msg)
    return package_root
