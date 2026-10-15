"""End-to-end contract for the installed console commands.

``test_readiness.py`` pins the entry-point *mappings* and calls ``main()``
in-process. Neither can catch a defect that only appears once the package is
built, installed, and invoked through its generated console-script shim — which
is the boundary this module exists to fix: ``uv tool install`` resolving the
commands a user actually runs.

Each test here builds the wheel from the working tree, installs it into a
throwaway virtual environment, and runs the real command. The environment is
isolated by ``UV_CACHE_DIR`` pointed at ``tmp_path``, so nothing reads or
writes the developer's own cache, and the suite stays hermetic.

The commands are run with ``PYTHONPATH`` and ``PYTHONHOME`` removed. That is
load-bearing rather than tidiness: ``test_readiness.py`` imports the project
from the source tree, so if pytest were started in a way that exports the
repository root on ``PYTHONPATH``, the subprocess would import
``src/voxel_forge`` and the test would pass without the wheel ever being
imported — exactly the defect class it exists to detect.

These are the slowest tests in the repository because each one builds a wheel.
They are worth that cost: the defect class they guard — a command that is
mapped correctly in ``pyproject.toml`` but does not work when installed — is
invisible to every faster test.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import os
import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

# The smoke test only needs the interpreter and the command under test, so the
# build is allowed generous headroom on a loaded machine without letting a
# genuine hang run forever.
BUILD_TIMEOUT_SECONDS = 600
COMMAND_TIMEOUT_SECONDS = 120

IS_WINDOWS = sys.platform == "win32"

# A venv puts its interpreter and console scripts in ``Scripts\\`` on Windows
# and in ``bin/`` elsewhere, and Windows names the interpreter ``python.exe``.
# Hardcoding the POSIX layout would make the fixture fail on Windows before any
# command was ever run.
VENV_BIN = Path("Scripts" if IS_WINDOWS else "bin")
VENV_PYTHON = VENV_BIN / ("python.exe" if IS_WINDOWS else "python")

# The commands are console-script shims; on Windows they carry a ``.exe`` (and
# a ``.cmd``) suffix, so existence has to be checked per platform.
COMMAND_SUFFIXES = (".exe", ".cmd", "") if IS_WINDOWS else ("",)


def installed_command(bin_dir: Path, name: str) -> Path:
    """Return the installed path of ``name``, or fail naming what was searched.

    ``shutil.which`` is not enough here: it would find an identically named
    command already on the host ``PATH`` and so could pass without the wheel
    having installed anything. Only candidates inside ``bin_dir`` count.
    """
    candidates = [bin_dir / f"{name}{suffix}" for suffix in COMMAND_SUFFIXES]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    msg = f"installing the wheel did not create {name}; looked for {candidates}"
    raise AssertionError(msg)


@dataclasses.dataclass(frozen=True, slots=True)
class _CommandResult:
    """Captured status and output from a task-owned command."""

    returncode: int
    stdout: str
    stderr: str


async def _execute_command(
    args: list[str], env: dict[str, str], timeout: int, *, capture: bool = True
) -> _CommandResult:
    """Run an argument vector directly, with bounded owned-process cleanup."""
    process = await asyncio.create_subprocess_exec(
        *args,
        cwd=REPOSITORY_ROOT,
        env=env,
        stdout=asyncio.subprocess.PIPE if capture else None,
        stderr=asyncio.subprocess.PIPE if capture else None,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout)
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()
    return _CommandResult(
        process.returncode, (stdout or b"").decode(), (stderr or b"").decode()
    )


@pytest.fixture(scope="module")
def installed_commands(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Build the wheel, install it into a throwaway environment, return its ``bin``.

    Module-scoped because the build and install are identical for every test
    in the file; the assertions differ only in which command each one runs.
    """
    workspace = tmp_path_factory.mktemp("installed-commands")
    environment = workspace / "venv"
    wheel_dir = workspace / "wheels"
    cache = workspace / "cache"

    def run(args: list[str], *, capture: bool = False) -> _CommandResult:
        return asyncio.run(
            _execute_command(
                args,
                {**os.environ, "UV_CACHE_DIR": str(cache)},
                BUILD_TIMEOUT_SECONDS,
                capture=capture,
            )
        )

    built = run(["uv", "build", "--wheel", "--out-dir", str(wheel_dir)], capture=True)
    assert built.returncode == 0, f"uv build failed:\n{built.stdout}\n{built.stderr}"

    wheels = sorted(wheel_dir.glob("voxel_forge-*.whl"))
    assert len(wheels) == 1, (
        f"expected exactly one wheel, found {[w.name for w in wheels]}"
    )

    created = run(["uv", "venv", "--python", "3.11", str(environment)], capture=True)
    assert created.returncode == 0, (
        f"uv venv failed:\n{created.stdout}\n{created.stderr}"
    )

    installed = run(
        [
            "uv",
            "pip",
            "install",
            "--python",
            str(environment / VENV_PYTHON),
            str(wheels[0]),
        ],
        capture=True,
    )
    assert installed.returncode == 0, (
        f"uv pip install failed:\n{installed.stdout}\n{installed.stderr}"
    )

    bin_dir = environment / VENV_BIN
    for command in ("voxel-forge", "voxel-forge-mcp", "voxel-forge-bridge"):
        installed_command(bin_dir, command)
    return bin_dir


def run_installed(command: Path, *args: str) -> _CommandResult:
    """Run an installed command in an environment that can only see the wheel.

    ``PYTHONPATH`` and ``PYTHONHOME`` are dropped so the interpreter cannot
    fall back to the source tree, and ``PYTHONNOUSERSITE`` keeps a user site
    directory from supplying ``voxel_forge`` instead of the venv. Everything
    else, in particular ``PATH`` and the venv's own variables, is preserved.
    """
    env = {k: v for k, v in os.environ.items() if k not in {"PYTHONPATH", "PYTHONHOME"}}
    env["PYTHONNOUSERSITE"] = "1"
    return asyncio.run(
        _execute_command([str(command), *args], env, COMMAND_TIMEOUT_SECONDS)
    )


def test_installed_mcp_command_answers_help(installed_commands: Path) -> None:
    """The installed ``voxel-forge-mcp --help`` must exit 0 and print usage.

    This is the roadmap 1.1.1 success criterion, asserted against the command
    a user installs rather than against ``server.main()`` in-process. Before
    this branch, the installed command ignored its arguments and blocked on
    stdio, so ``--help`` never returned.
    """
    completed = run_installed(
        installed_command(installed_commands, "voxel-forge-mcp"), "--help"
    )

    assert completed.returncode == 0, (
        f"--help must succeed, got {completed.returncode}:\n{completed.stderr}"
    )
    assert "VoxelForge" in completed.stdout, "usage must name the server it describes"
    assert "usage:" in completed.stdout, "help must print usage"
    assert not completed.stderr, (
        "a help query must not start the bridge and report its ports"
    )


def test_installed_desktop_command_degrades_without_the_extra(
    installed_commands: Path,
    desktop_extra_hint: str,
) -> None:
    """The installed ``voxel-forge`` must degrade cleanly when PySide6 is absent.

    This is the roadmap 1.1.2 success criterion. The throwaway environment
    installs the base package without the ``desktop`` extra, which is exactly
    the state a user is in after a plain ``uv tool install``. The command must
    name the missing extra and exit non-zero *without* a traceback; before this
    branch it resolved straight to the PySide6-backed application and died with
    an ``ImportError`` traceback instead.
    """
    completed = run_installed(installed_command(installed_commands, "voxel-forge"))

    assert completed.returncode != 0, (
        "the command must report failure, not exit silently as if it had started"
    )
    assert completed.stderr == desktop_extra_hint.format(missing="PySide6"), (
        "the installed command must give the complete portable extra-install guidance"
    )


def test_installed_js_root_resolves_wheel_assets(installed_commands: Path) -> None:
    """The module command must resolve the installed package rather than checkout."""
    completed = run_installed(
        installed_commands / VENV_PYTHON.name, "-m", "voxel_forge.js_root"
    )
    assert completed.returncode == 0, completed.stderr
    root = Path(completed.stdout.strip())
    assert root.is_relative_to(installed_commands.parent), (
        "the command must locate assets inside the installed virtual environment"
    )
    assert (root / "serve.ts").is_file(), "the wheel must include the Bun entrypoint"
    assert (root / "package.json").is_file(), (
        "the installed root must contain its manifest"
    )


@pytest.mark.skipif(IS_WINDOWS, reason="PATH-scoped POSIX executable Bun stub")
def test_installed_dependency_helper_invokes_bun_without_network(
    installed_commands: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The installed helper must invoke Bun against packaged assets without fetching."""
    python = installed_commands / VENV_PYTHON.name
    recorder = tmp_path / "bun-arguments.json"
    stub = tmp_path / "bun"
    stub.write_text(
        f"#!{python}\n"
        "import json, os, pathlib, sys\n"
        "pathlib.Path(os.environ['VOXELFORGE_TEST_INSTALL_ARGS']).write_text("
        "json.dumps(sys.argv[1:]), encoding='utf-8')\n",
        encoding="utf-8",
    )
    stub.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.environ.get("PATH", ""))
    monkeypatch.setenv("VOXELFORGE_TEST_INSTALL_ARGS", str(recorder))
    monkeypatch.delenv("BUN", raising=False)

    completed = run_installed(python, "-m", "voxel_forge.install_editor_deps")
    assert completed.returncode == 0, completed.stderr
    args = json.loads(recorder.read_text(encoding="utf-8"))
    assert args[:2] == ["install", "--cwd"], (
        "invoke Bun's dependency installation command"
    )
    root = Path(args[2])
    assert root.is_relative_to(installed_commands.parent), (
        "install dependencies into the installed package, never the checkout"
    )
    assert (root / "package.json").is_file(), (
        "the target must contain the wheel manifest"
    )
