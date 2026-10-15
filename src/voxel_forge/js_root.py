"""Command-line helper for resolving the bundled editor's package root.

Mirrors simulacat's ``js_root`` module: a stable command for shell
scripts and continuous integration::

    python -m voxel_forge.js_root

It prints the absolute directory containing the editor's
``package.json``, suitable for ``bun install --cwd ...``.
"""

from __future__ import annotations

import sys

from voxel_forge.editor_runtime import EditorRuntimeError, editor_package_root


def main() -> int:
    """Resolve and print the editor's JavaScript package root.

    Returns
    -------
    int
        ``0`` when resolution succeeds and the package root path is
        written to stdout; otherwise ``1`` after writing an error
        message to stderr.

    Examples
    --------
    Resolve the root from a shell::

        $ python -m voxel_forge.js_root
        /path/to/site-packages/voxel_forge/editor
    """
    try:
        package_root = editor_package_root()
    except EditorRuntimeError as exc:
        print(f"Failed to resolve the editor package root: {exc}", file=sys.stderr)
        return 1

    print(package_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
