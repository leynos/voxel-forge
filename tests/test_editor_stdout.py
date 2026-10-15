"""Bounded stdout handling before and after the editor reports readiness."""

from __future__ import annotations

import logging
import subprocess  # ruff: ignore[suspicious-subprocess-import]  # fixed interpreter fixtures; shell=False
import sys
import typing as typ

import pytest

from voxel_forge import orchestration
from voxel_forge.editor_runtime import EditorRuntimeError

if typ.TYPE_CHECKING:
    import queue
    import threading


def test_output_after_readiness_is_drained_without_queue_growth(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Readiness must hand stdout over to a bounded drain."""
    observed: list[tuple[queue.Queue[str | None], threading.Thread]] = []
    original = orchestration._start_stdout_reader

    def observe_reader(
        process: subprocess.Popen[str],
        startup_finished: threading.Event | None = None,
    ) -> tuple[queue.Queue[str | None], threading.Thread]:
        """Observe the reader queue while preserving the production startup protocol."""
        result = (
            original(process)
            if startup_finished is None
            else original(process, startup_finished)
        )
        observed.append(result)
        return result

    monkeypatch.setattr(orchestration, "_start_stdout_reader", observe_reader)
    caplog.set_level(logging.INFO, logger="voxel_forge.orchestration")
    script = (
        "import json, sys; "
        "print(json.dumps(dict(event='listening', port=43210)), flush=True); "
        "sys.stdin.readline(); "
        "[print('private-child-output' * 100) for _ in range(2048)]"
    )
    with subprocess.Popen(  # ruff: ignore[subprocess-without-shell-equals-true]  # fixed interpreter and script; shell=False
        [sys.executable, "-c", script],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    ) as process:
        try:
            assert orchestration._wait_for_port(process, 5) == 43210, (
                "consume readiness first"
            )
            assert process.stdin is not None, (
                "the fixture needs a controlled output trigger"
            )
            process.stdin.write("emit output\n")
            process.stdin.close()
            process.wait(timeout=5)
            line_queue, reader = observed[0]
            reader.join(timeout=5)
            assert not reader.is_alive(), "drain the pipe through child exit"
            assert line_queue.qsize() <= 64, "post-readiness output must not accumulate"
            assert line_queue.maxsize > 0, "the startup channel must itself be bounded"
            messages = [record.getMessage() for record in caplog.records]
            assert any("stdout" in message for message in messages), (
                "record bounded drain diagnostics"
            )
            assert all("private-child-output" not in message for message in messages), (
                "child output must never be copied into lifecycle logs"
            )
        finally:
            orchestration.stop_editor_process(process)


def test_startup_error_diagnostics_are_bounded() -> None:
    """A noisy child failing startup must not create an unbounded exception message."""
    with subprocess.Popen(
        [sys.executable, "-c", "[print('x' * 4096) for _ in range(100)]"],
        stdout=subprocess.PIPE,
        text=True,
    ) as process:
        try:
            with pytest.raises(
                EditorRuntimeError, match="did not report a listening port"
            ) as caught:
                orchestration._wait_for_port(process, 5)
            assert len(str(caught.value)) <= 64 * 4096 + 256, (
                "retain only the bounded startup diagnostic tail"
            )
        finally:
            orchestration.stop_editor_process(process)
