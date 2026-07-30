"""Install the bundled editor's JavaScript dependencies.

Mirrors simulacat's ``install_simulator_deps`` module: one command that
continuous integration and shell scripts can run knowing only the
installed Python package::

    python -m voxel_forge.install_editor_deps

It resolves the bundled editor's package root and runs ``bun install``
against it.
"""

from __future__ import annotations

import sys

from voxel_forge.editor_runtime import EditorRuntimeError
from voxel_forge.orchestration import install_editor_dependencies


def main() -> int:
    """Run dependency installation and return a process exit code.

    Returns
    -------
    int
        ``0`` when dependency installation succeeds; otherwise ``1``
        after writing an error message to stderr.

    Examples
    --------
    Install the editor's dependencies from a shell::

        $ python -m voxel_forge.install_editor_deps
        Installed editor dependencies in /path/to/voxel_forge/editor
    """
    try:
        package_root = install_editor_dependencies()
    except EditorRuntimeError as exc:
        print(f"Failed to install editor dependencies: {exc}", file=sys.stderr)
        return 1

    print(f"Installed editor dependencies in {package_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
