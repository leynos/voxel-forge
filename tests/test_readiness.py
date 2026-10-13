"""Executable contract for the readiness gates.

Each test here pins one behaviour that "basic agent-driven voxel scene creation"
depends on: the MCP launcher, bridge scheduling and origin checks, editor
removal round-trips, scene-name and payload validation, resource bounds,
persistence, and the raw structure of exported MagicaVoxel files.

Run the whole module with ``uv run pytest -q``. Tests that touch persistence
request the ``scene_directory`` fixture from ``conftest.py`` so no real
``~/.voxel-forge`` directory is read or written. Assertions carry messages
because a readiness failure should name the broken contract directly.
"""

from __future__ import annotations

import contextlib
import sys
from pathlib import Path
from types import ModuleType

import pytest

from voxel_forge import server

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_desktop_entry_point_degrades_without_pyside6(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    desktop_extra_hint: str,
) -> None:
    """Without the `desktop` extra, `voxel-forge` must explain, not traceback."""
    monkeypatch.setitem(sys.modules, "PySide6", None)
    monkeypatch.setitem(sys.modules, "PySide6.QtCore", None)
    monkeypatch.delitem(sys.modules, "voxel_forge.desktop.app", raising=False)
    from voxel_forge.desktop import launch

    exit_code = launch.main()
    captured = capsys.readouterr()

    assert exit_code == 1, "a missing GUI extra must return a failing exit status"
    assert captured.err == desktop_extra_hint.format(missing="PySide6.QtCore"), (
        "a missing extra must provide the complete portable recovery message"
    )


def test_desktop_entry_point_propagates_unrelated_import_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An app.py import that fails for another reason must surface, not be misreported.

    Halting the module forces the failure before any PySide6 import could run,
    so the guard must decline it in every environment, whether or not the
    ``desktop`` extra is installed.
    """
    monkeypatch.setitem(sys.modules, "voxel_forge.desktop.app", None)
    from voxel_forge.desktop import launch

    with pytest.raises(ImportError, match=r"voxel_forge\.desktop\.app"):
        launch.main()


@pytest.mark.parametrize(
    ("error", "is_desktop_extra_failure"),
    [
        # The extra is absent: CPython names the missing distribution, or a
        # dotted submodule once the top-level package itself is present.
        (ImportError("No module named 'PySide6'", name="PySide6"), True),
        (
            ImportError(
                "import of PySide6.QtCore halted; None in sys.modules",
                name="PySide6.QtCore",
            ),
            True,
        ),
        (ImportError("No module named 'shiboken6'", name="shiboken6"), True),
        # PySide6 is installed but its native stack cannot load, which a
        # headless Linux runner reaches through Qt's EGL dependency. CPython
        # names the leaf extension instead, and that traceback is the only
        # thing that identifies the missing library, so it must not be
        # replaced by advice to install an extra that is already there.
        (
            ImportError(
                (
                    "libEGL.so.1: cannot open shared object file: No su"
                    "ch file or directory"
                ),
                name="QtCore",
                path="/venv/site-packages/PySide6/QtCore.abi3.so",
            ),
            False,
        ),
        (
            ImportError(
                "No module named 'voxel_forge.export_roblox'",
                name="voxel_forge.export_roblox",
            ),
            False,
        ),
        (ImportError("desktop import failed without naming a module"), False),
    ],
)
def test_desktop_extra_failure_classification(
    error: ImportError, *, is_desktop_extra_failure: bool
) -> None:
    """Each import failure is classified as the missing extra, or not."""
    from voxel_forge.desktop import launch

    assert launch._names_missing_desktop_extra(error) is is_desktop_extra_failure, (
        "only missing optional distributions should be classified as an absent extra"
    )


def test_runtime_dependencies_are_bounded_below_next_major() -> None:
    """A fresh resolution (``uv tool install``) must not select a breaking major.

    The caps are the versions each library is known to break at, which is not
    always the next major above the floor: ``mcp`` and ``httpx`` break at
    their next major, while ``websockets`` breaks at 17. Asserting the exact
    intended cap rather than the presence of a ``<`` keeps a typo such as
    ``mcp>=1.9.0,<3`` from passing while it permits the incompatible 2.x line
    the bound exists to exclude.
    """
    import tomllib

    expected_caps = {"mcp": "2", "websockets": "17", "httpx": "1"}
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    declared: dict[str, str] = {}
    for requirement in pyproject["project"]["dependencies"]:
        name, _, specifier = requirement.partition(">=")
        assert specifier, f"dependency {requirement!r} has no lower bound"
        declared[name] = specifier

    assert set(declared) == set(expected_caps), (
        f"runtime dependency set changed: {sorted(declared)}"
    )

    for name, expected_cap in expected_caps.items():
        _, _, upper = declared[name].partition(",")
        assert upper == f"<{expected_cap}", (
            f"{name}"
            " must be capped at <"
            f"{expected_cap}"
            ", found "
            f"{upper or 'no upper bound'}"
        )


def test_desktop_entry_point_runs_the_application_on_the_happy_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With the extra present, `voxel-forge` must actually run the desktop app.

    A fake ``voxel_forge.desktop.app`` stands in for the real module, so the
    check holds whether or not PySide6 is installed. The assertion is on the
    call, not only the exit code: a launcher that returned 0 without running
    anything would otherwise pass while doing nothing at all.
    """
    ran: list[str] = []

    class DesktopModule(ModuleType):
        """A desktop module with a declared entry point that records execution."""

        def main(self) -> None:
            """Record the launcher's call to the application entry point."""
            ran.append("ran")

    fake_app = DesktopModule("voxel_forge.desktop.app")
    monkeypatch.setitem(sys.modules, "voxel_forge.desktop.app", fake_app)
    from voxel_forge.desktop import launch

    exit_code = launch.main()

    assert ran == ["ran"], "the launcher must call the desktop application"
    assert exit_code == 0, "a successful desktop launch must report success"


@pytest.mark.parametrize("arguments", [["--help"], []], ids=["help", "startup"])
def test_mcp_entry_point_obeys_its_arguments(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    mcp_invocations: tuple[list[str], list[str]],
    arguments: list[str],
) -> None:
    """Help exits before binding; ordinary startup launches the bridge then stdio."""
    monkeypatch.setattr(sys, "argv", ["voxel-forge-mcp", *arguments])
    calls, transports = mcp_invocations
    expectation = pytest.raises(SystemExit) if arguments else contextlib.nullcontext()
    with expectation as exit_info:
        server.main()
    if arguments:
        assert exit_info is not None, "help must terminate through argument parsing"
        assert exit_info.value.code == 0, "MCP help must exit successfully"
        assert "VoxelForge" in capsys.readouterr().out, (
            "help must identify the application"
        )
        assert not calls, "help must not start the bridge or server"
    else:
        assert calls == ["bridge", "run"], "startup must launch the bridge before stdio"
        assert transports == ["stdio"], "the MCP server must use its protocol transport"
