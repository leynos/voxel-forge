"""Behavioural checks for lint failure propagation and runtime compatibility."""

from __future__ import annotations

import asyncio
import os
import shlex
import shutil
from pathlib import Path

import pytest

_REPOSITORY = Path(__file__).resolve().parents[1]


def _run_make(
    arguments: list[str], *, env: dict[str, str] | None = None
) -> tuple[int, str]:
    """Drive test-only Make probes with an argument vector and a bounded wait."""
    make = shutil.which("make")
    assert make is not None, "Make is required for contributor gates"

    async def run() -> tuple[int, str]:
        """Run make to completion and return its exit code and combined output."""
        process = await asyncio.create_subprocess_exec(
            make,
            "--no-print-directory",
            *arguments,
            cwd=_REPOSITORY,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        try:
            output, _ = await asyncio.wait_for(process.communicate(), timeout=120)
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()
        assert process.returncode is not None, "Make must have finished"
        return process.returncode, output.decode()

    return asyncio.run(run())


@pytest.mark.parametrize(
    "failed_stage",
    [
        "ruff check",
        "pylint --load-plugins= src",
        "--load-plugins=df12_python_lints",
        "df12-skylos check",
        "df12-duplication install",
        "df12-duplication check",
    ],
)
def test_lint_stops_when_any_gate_fails(tmp_path: Path, failed_stage: str) -> None:
    """Every blocking stage must stop Make before subsequent tools execute."""
    probe = tmp_path / "uv"
    probe.write_text(
        '#!/bin/sh\nprintf "%s\\n" "$*" >> "$PROBE_LOG"\n'
        'case "$*" in *"$PROBE_FAIL"*) exit 1;; esac\n',
        encoding="utf-8",
    )
    probe.chmod(0o700)
    log = tmp_path / "calls.log"
    env = os.environ.copy()
    env.update(
        PATH=f"{tmp_path}{os.pathsep}{env['PATH']}",
        PROBE_LOG=str(log),
        PROBE_FAIL=failed_stage,
    )

    returncode, output = _run_make(["lint"], env=env)

    assert returncode != 0, f"a failed lint stage must fail Make: {output}"
    assert log.is_file(), "Make must invoke the fake uv before failing"
    calls = log.read_text(encoding="utf-8").splitlines()
    assert calls, "the fake uv must record at least one invocation"
    assert failed_stage in calls[-1], "no tool may execute after the failed stage"
    assert sum(failed_stage in call for call in calls) == 1, (
        "the failing tool must be invoked exactly once"
    )


@pytest.mark.parametrize(
    ("source", "is_valid"),
    [
        ('"""A clean module."""\nVALUE = 1\n', True),
        ("def broken(\n    return 1\n", False),
    ],
)
def test_base_pylint_rejects_unparsable_source(
    tmp_path: Path, source: str, *, is_valid: bool
) -> None:
    """The real PyPy lint tier must reject syntax errors and accept valid code."""
    module = tmp_path / "probe.py"
    module.write_text(source, encoding="utf-8")
    quoted_module = shlex.quote(str(module)).replace("$", "$$")

    returncode, output = _run_make(
        [
            "--eval",
            f"lint-probe: ; $(PYLINT) {quoted_module}",
            "lint-probe",
        ],
    )

    assert (returncode == 0) is is_valid, (
        f"the parser gate must distinguish valid and broken source: {output}"
    )
    if not is_valid:
        assert "syntax-error" in output, "the parse failure must be reported"
