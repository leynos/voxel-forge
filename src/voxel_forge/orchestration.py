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
import collections
import contextlib
import dataclasses as dc
import json
import logging
import os
import queue
import subprocess  # ruff: ignore[suspicious-subprocess-import]  # spawn Bun with validated arguments; shell=False
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

_LOG = logging.getLogger(__name__)

DEFAULT_STOP_TIMEOUT_SECONDS = 5.0
DEFAULT_STARTUP_TIMEOUT_SECONDS = 30.0
_POLL_JOIN_TIMEOUT_SECONDS = 0.1
_MAX_STARTUP_OUTPUT_LINES = 64
_MAX_STDOUT_CHUNK_CHARS = 4096


@dc.dataclass(frozen=True, slots=True)
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
    env["VOXELFORGE_EDITOR_SUPERVISED"] = "1"
    try:
        return subprocess.Popen(  # ruff: ignore[subprocess-without-shell-equals-true]  # validated executable and script path; shell=False
            [bun_executable, str(editor_entrypoint())],
            # EOF gives Bun a parent-death signal, including on Windows.
            stdin=subprocess.PIPE,
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


def _queue_startup_line(
    line_queue: queue.Queue[str | None],
    startup_finished: threading.Event,
    line: str | None,
) -> None:
    """Publish startup output with backpressure until its consumer finishes."""
    while not startup_finished.is_set():
        try:
            line_queue.put(line, timeout=_POLL_JOIN_TIMEOUT_SECONDS)
        except queue.Full:
            continue
        else:
            return


def _start_stdout_reader(
    process: subprocess.Popen[str],
    startup_finished: threading.Event | None = None,
) -> tuple[queue.Queue[str | None], threading.Thread]:
    """Queue bounded startup output, then drain subsequent output without retention.

    The startup consumer signals completion even when it raises. That signal
    releases queue backpressure, so the reader keeps draining Bun without
    retaining output for a consumer that no longer exists. Diagnostics report
    activity once and omit child content, which may contain private scene data.
    """
    stdout = process.stdout
    if stdout is None:
        msg = "Failed to capture editor stdout"
        raise EditorRuntimeError(msg)

    finished = startup_finished if startup_finished is not None else threading.Event()
    line_queue: queue.Queue[str | None] = queue.Queue(maxsize=_MAX_STARTUP_OUTPUT_LINES)

    def _reader() -> None:
        """Drain fixed-size chunks throughout the child lifetime."""
        has_reported_output = False
        while line := stdout.readline(_MAX_STDOUT_CHUNK_CHARS):
            if finished.is_set():
                if not has_reported_output:
                    _LOG.info(
                        "Editor stdout drained pid=%d (content omitted)", process.pid
                    )
                    has_reported_output = True
            else:
                _queue_startup_line(line_queue, finished, line)
        _queue_startup_line(line_queue, finished, None)

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
    output_lines: collections.deque[str] = collections.deque(
        maxlen=_MAX_STARTUP_OUTPUT_LINES
    )
    deadline = time.monotonic() + startup_timeout
    startup_finished = threading.Event()
    line_queue, reader = _start_stdout_reader(process, startup_finished)

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
        startup_finished.set()
        reader.join(timeout=_POLL_JOIN_TIMEOUT_SECONDS)

    msg = (
        "Editor did not report a listening port.\n"
        f"Exit code: {process.poll()}\n"
        f"Output (last {_MAX_STARTUP_OUTPUT_LINES} chunks):\n{''.join(output_lines)}"
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
    _LOG.info("Editor starting pid=%d", process.pid)
    is_ready = False
    try:
        port = _wait_for_port(process, startup_timeout)
        is_ready = True
        _LOG.info("Editor listening pid=%d port=%d", process.pid, port)
        return process, port
    finally:
        # Cleanup also covers cancellation and malformed startup events.
        if not is_ready:
            _LOG.warning("Editor startup failed pid=%d", process.pid)
            stop_editor_process(process, timeout=1.0)


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
        _LOG.warning(
            "Editor terminate timed out; escalating to kill pid=%d", process.pid
        )
        with contextlib.suppress(OSError):
            process.kill()
        with contextlib.suppress(subprocess.TimeoutExpired, OSError):
            process.wait(timeout=timeout)
    if process.poll() is None:
        _LOG.error("Editor remains alive after terminate and kill pid=%d", process.pid)
    else:
        _LOG.info("Editor stopped pid=%d status=%d", process.pid, process.returncode)
    with _supervised_lock:
        if process.poll() is not None and _supervised.get(process.pid) is process:
            del _supervised[process.pid]


_supervised: dict[int, subprocess.Popen[str]] = {}
_supervised_lock = threading.Lock()


def supervise(process: subprocess.Popen[str]) -> None:
    """Register a live process and release completed supervision handles."""
    with _supervised_lock:
        exited = [pid for pid, child in _supervised.items() if child.poll() is not None]
        for pid in exited:
            del _supervised[pid]
        if process.poll() is None:
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
            command, check=False, timeout=_INSTALL_TIMEOUT_SECONDS
        )
    except FileNotFoundError as exc:
        msg = f"Bun executable not found: {executable}"
        raise EditorRuntimeError(msg) from exc
    except subprocess.TimeoutExpired as exc:
        msg = (
            "Timed out installing editor dependencies after "
            f"{_INSTALL_TIMEOUT_SECONDS}s with command: {' '.join(command)}"
        )
        raise EditorRuntimeError(msg) from exc
    if result.returncode != 0:
        msg = f"Failed to install editor dependencies with command: {' '.join(command)}"
        raise EditorRuntimeError(msg)
    return package_root
