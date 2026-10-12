"""End-to-end contract for the installed console commands.

``test_readiness.py`` pins the entry-point *mappings* and calls ``main()``
in-process. Neither can catch a defect that only appears once the package is
built, installed, and invoked through its generated console-script shim — which
is the boundary this module exists to fix: ``uv tool install`` resolving the
commands a user actually runs.

Each test here builds the wheel from the working tree, installs it into a
throwaway virtual environment, and runs the real command. The environment is
isolated by ``UV_PROJECT_ENVIRONMENT`` and ``UV_CACHE_DIR`` pointed at
``tmp_path``, so nothing reads or writes the developer's own environments or
cache, and the suite stays hermetic.

These are the slowest tests in the repository because each one builds a wheel.
They are worth that cost: the defect class they guard — a command that is
mapped correctly in ``pyproject.toml`` but does not work when installed — is
invisible to every faster test.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

# The smoke test only needs the interpreter and the command under test, so the
# build is allowed generous headroom on a loaded machine without letting a
# genuine hang run forever.
BUILD_TIMEOUT_SECONDS = 600
COMMAND_TIMEOUT_SECONDS = 120


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

    def run(args: list[str], *, capture: bool = False) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            args,
            cwd=REPOSITORY_ROOT,
            check=False,
            text=True,
            timeout=BUILD_TIMEOUT_SECONDS,
            capture_output=capture,
            env={**os.environ, "UV_CACHE_DIR": str(cache)},
        )

    built = run(["uv", "build", "--wheel", "--out-dir", str(wheel_dir)], capture=True)
    assert built.returncode == 0, f"uv build failed:\n{built.stdout}\n{built.stderr}"

    wheels = sorted(wheel_dir.glob("voxel_forge-*.whl"))
    assert len(wheels) == 1, f"expected exactly one wheel, found {[w.name for w in wheels]}"

    created = run(["uv", "venv", "--python", "3.11", str(environment)], capture=True)
    assert created.returncode == 0, f"uv venv failed:\n{created.stdout}\n{created.stderr}"

    installed = run(
        ["uv", "pip", "install", "--python", str(environment / "bin" / "python"), str(wheels[0])],
        capture=True,
    )
    assert installed.returncode == 0, f"uv pip install failed:\n{installed.stdout}\n{installed.stderr}"

    bin_dir = environment / "bin"
    for command in ("voxel-forge", "voxel-forge-mcp", "voxel-forge-bridge"):
        assert (bin_dir / command).exists(), f"installing the wheel did not create the {command} command"
    return bin_dir


def test_installed_mcp_command_answers_help(installed_commands: Path) -> None:
    """The installed ``voxel-forge-mcp --help`` must exit 0 and print usage.

    This is the roadmap 1.1.1 success criterion, asserted against the command
    a user installs rather than against ``server.main()`` in-process. Before
    this branch, the installed command ignored its arguments and blocked on
    stdio, so ``--help`` never returned.
    """
    completed = subprocess.run(
        [str(installed_commands / "voxel-forge-mcp"), "--help"],
        check=False,
        text=True,
        capture_output=True,
        timeout=COMMAND_TIMEOUT_SECONDS,
    )

    assert completed.returncode == 0, f"--help must succeed, got {completed.returncode}:\n{completed.stderr}"
    assert "VoxelForge" in completed.stdout, "usage must name the server it describes"
    assert "usage:" in completed.stdout, "help must print usage"
    assert completed.stderr == "", "a help query must not start the bridge and report its ports"


def test_installed_desktop_command_degrades_without_the_extra(installed_commands: Path) -> None:
    """The installed ``voxel-forge`` must degrade cleanly when PySide6 is absent.

    This is the roadmap 1.1.2 success criterion. The throwaway environment
    installs the base package without the ``desktop`` extra, which is exactly
    the state a user is in after a plain ``uv tool install``. The command must
    name the missing extra and exit non-zero *without* a traceback; before this
    branch it resolved straight to the PySide6-backed application and died with
    an ``ImportError`` traceback instead.
    """
    completed = subprocess.run(
        [str(installed_commands / "voxel-forge")],
        check=False,
        text=True,
        capture_output=True,
        timeout=COMMAND_TIMEOUT_SECONDS,
    )

    assert completed.returncode != 0, "the command must report failure, not exit silently as if it had started"
    assert "desktop" in completed.stderr, "the message must name the missing optional extra"
    assert "PySide6" in completed.stderr, "the message must name the dependency that is actually missing"
    assert "uv tool install" in completed.stderr, "the message must give the command that fixes it"
    assert "Traceback" not in completed.stderr, "a missing optional extra is an expected state, not a crash"
