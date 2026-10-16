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

import typing as typ

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    import pytest

from pathlib import Path

import voxel_forge
from voxel_forge import server

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _prepare_editor_tool(
    monkeypatch: pytest.MonkeyPatch,
    start_editor: cabc.Callable[[tuple[int, int]], tuple[object, int]],
) -> list[str]:
    """Replace bridge, process, and browser effects for launcher tests."""
    import webbrowser

    from voxel_forge import bridge
    from voxel_forge.server_tools import io

    monkeypatch.setattr(server, "_ensure_bridge", lambda _trigger: None)
    monkeypatch.setattr(bridge, "current_ports", lambda: (43001, 43002))
    monkeypatch.setattr(io, "_running_editor", lambda: None)
    monkeypatch.setattr(io, "_start_supervised_editor", start_editor)
    opened: list[str] = []
    monkeypatch.setattr(webbrowser, "open", opened.append)
    return opened


def test_installed_entry_points_target_the_launchers() -> None:
    """The installed commands must map to the modules this branch makes correct.

    ``voxel-forge`` pointing at the desktop application directly is the defect
    this branch fixes: without the optional extra the command then died with a
    traceback instead of an explanation. Pinning the target here means the
    regression cannot return unnoticed, because the mapping itself is asserted
    rather than only the behaviour of the module it names.
    """
    import tomllib

    pyproject = tomllib.loads(
        (REPOSITORY_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )

    assert pyproject["project"]["scripts"] == {
        "voxel-forge": "voxel_forge.desktop.launch:main",
        "voxel-forge-mcp": "voxel_forge.server:main",
        "voxel-forge-bridge": "voxel_forge.bridge:main",
    }, "installed commands must retain their guarded entry points"


def test_migration_document_matches_the_declared_version() -> None:
    """The migration document, the package version, and the lockfile must agree.

    This branch changes the installed commands, so it needs a migration
    document. A document named for a version the package does not have is worse
    than none: it describes a release that does not exist and is not the file a
    reader upgrading to the real version would open. Asserting all three
    together is what keeps the name, the metadata, and the lock in step when
    the version moves again.

    Every path is resolved from ``REPOSITORY_ROOT`` rather than the current
    working directory, so the test reads the same files whatever directory
    pytest was invoked from. A relative path here would silently test nothing
    if the suite were ever run from elsewhere, since the reads would raise
    ``FileNotFoundError`` against files that do exist in the repository.
    """
    import tomllib

    pyproject = tomllib.loads(
        (REPOSITORY_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    version = pyproject["project"]["version"]
    assert version == voxel_forge.__version__, (
        "pyproject declares "
        f"{version}"
        " but the package reports "
        f"{voxel_forge.__version__}"
    )

    # A migration document is named for the release line (``0.2``), not the
    # full patch version, so one file covers every patch in that line.
    release_line = ".".join(version.split(".")[:2])
    # Kept relative for the Makefile comparison below, which lists its inputs
    # relative to the repository root, and made absolute for reading, so the
    # test works whatever directory pytest was invoked from.
    migration_relative = f"docs/migration-{release_line}.md"
    migration = REPOSITORY_ROOT / migration_relative
    assert migration.is_file(), (
        f"version {version} has no migration document at {migration}"
    )

    lock = (REPOSITORY_ROOT / "uv.lock").read_text(encoding="utf-8")
    assert f'name = "voxel-forge"\nversion = "{version}"' in lock, (
        f"uv.lock does not record voxel-forge at {version}; run `uv lock`"
    )

    # The document is only reachable if it is linked, and it is only validated
    # if the Markdown gate is pointed at it.
    makefile = (REPOSITORY_ROOT / "Makefile").read_text(encoding="utf-8")
    assert migration_relative in makefile, (
        f"{migration_relative} is not covered by the Markdown gate"
    )

    readme = (REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8")
    users_guide = (REPOSITORY_ROOT / "docs/users-guide.md").read_text(encoding="utf-8")
    assert migration.name in readme, f"README does not link {migration.name}"
    assert migration.name in users_guide, (
        f"the users guide does not link {migration.name}"
    )


def test_readme_documents_cross_platform_installation() -> None:
    """The README must be followable on Linux without translation."""
    readme = (REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8")

    assert "uv tool install" in readme, "README must explain portable installation"
    assert "voxel-forge-mcp" in readme, "README must identify the installed MCP command"
    assert "C:\\Users" not in readme, (
        "README must not rely on user-specific absolute paths"
    )


def _windows_launcher_offenders(root: Path) -> list[str]:
    """Find user-facing lines naming a ``.bat`` launcher without Windows context.

    Scanned across the README and the source modules rather than the README
    alone. A launcher named only in the README is the easiest case to catch,
    but the same string reaches users through tool output: an MCP tool result
    that says "use run-editor.bat" is read on Linux too, and no heading can
    qualify prose emitted from a function body.

    Planning records and tests are deliberately out of scope. An ExecPlan or a
    roadmap entry is a historical account of work, and a test docstring is
    explanation of a check -- neither is followed by a user as an instruction,
    so requiring Windows context there would force edits to records without
    protecting anyone. Only text presented as the thing to do is scanned.

    Context is established differently per file type. In the README a launcher
    reference inherits its enclosing heading, so a `.bat` named under a
    "### Build ... (Windows)" heading is qualified. In Python source a ``#``
    line is a comment, not a heading: it never reaches the user alongside the
    string, so it must not qualify one. A docstring or comment reading "# the
    Windows helper" would otherwise silence the check for the very string it
    fails to qualify -- confirmed by negative control, where a preceding
    ``# Windows helper is run-editor.bat`` comment let a user-visible
    ``run-editor.bat`` string pass. Python lines must therefore say Windows on
    the same line that names the launcher.

    Parameters
    ----------
    root : Path
        Repository root to scan.

    Returns
    -------
    list[str]
        ``path:line: text`` for each offending line, empty when none remain.
    """
    readme = root / "README.md"
    targets = [readme, *sorted((root / "src").rglob("*.py"))]
    offenders: list[str] = []

    for path in targets:
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue

        heading = ""
        for number, line in enumerate(text.splitlines(), start=1):
            if path == readme and line.lstrip().startswith("#"):
                heading = line
            if ".bat" not in line:
                continue
            if "windows" in f"{heading} {line}".lower():
                continue
            offenders.append(f"{path.relative_to(root)}:{number}: {line.strip()}")

    return offenders


def test_no_launcher_is_named_outside_windows_context() -> None:
    """A `.bat` reference must sit in Windows context, or it misleads Linux readers.

    Asserting only that the README mentions `voxel-forge-mcp` somewhere is too
    weak: the desktop section can name the Windows-only wrapper instead while
    the string still appears elsewhere, which is how `.bat` survived in a
    section whose whole purpose was the cross-platform path. Requiring the
    line, its enclosing heading, or the explanatory text on the line itself to
    establish Windows context keeps the wrappers documented as conveniences
    rather than as the general command.

    The scan covers emitted source strings as well as the README, because a
    Windows-only wrapper must not be presented to Linux callers as the general
    launcher command.
    """
    offenders = _windows_launcher_offenders(REPOSITORY_ROOT)

    assert not offenders, (
        "these lines name a Windows-only .bat launcher without saying so, "
        "which reads as the general instruction on Linux:\n  " + "\n  ".join(offenders)
    )


def test_launch_editor_tool_opens_supervised_editor_on_discovered_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The MCP tool should start the supervised editor and open its bound URL."""

    def start_editor(ports: tuple[int, int]) -> tuple[object, int]:
        assert ports == (43001, 43002), (
            "the editor must receive the bridge's dynamically bound ports"
        )
        return object(), 43003

    opened = _prepare_editor_tool(monkeypatch, start_editor)

    response = server.voxelforge_launch_editor()

    assert response == (
        "เปิด http://127.0.0.1:43003 แล้ว (Bun editor ภายใต้การดูแลของ server)\n"
        "Bridge: ws://127.0.0.1:43001 | HTTP scene: "
        "http://127.0.0.1:43002/scene"
    ), "the tool response must report the editor and both bridge endpoints"
    assert opened == ["http://127.0.0.1:43003"], (
        "the browser must open the editor's discovered port"
    )


def test_launch_editor_tool_reports_supervision_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed Bun startup should tell callers how to recover."""
    from voxel_forge.editor_runtime import EditorRuntimeError

    def fail_start(_ports: tuple[int, int]) -> tuple[object, int]:
        msg = "Bun executable not found"
        raise EditorRuntimeError(msg)

    opened = _prepare_editor_tool(monkeypatch, fail_start)

    response = server.voxelforge_launch_editor()

    assert response == (
        "ไม่สามารถเปิด editor ได้: Bun executable not found\n"
        "ติดตั้ง Bun (https://bun.sh) แล้วเรียก voxelforge_launch_editor อีกครั้ง"
    ), "a Bun startup failure must include the recovery instruction"
    assert not opened, "a failed startup must not launch the browser"


def test_windows_mcp_launcher_uses_installed_entrypoint() -> None:
    """The Windows launcher must use the installed command and return its status."""
    launcher = (REPOSITORY_ROOT / "run-mcp.bat").read_text(encoding="utf-8")

    assert "uv run voxel-forge-mcp" in launcher, (
        "the launcher must call the installed console script"
    )
    assert "python src/voxel_forge/server.py" not in launcher, (
        "the launcher must not run a source file directly"
    )
    assert "|| exit /b 1" in launcher, "a failed locked sync must abort the launcher"
    assert launcher.rstrip().endswith("exit /b %errorlevel%"), (
        "the launcher must return the exit status of the MCP server"
    )
