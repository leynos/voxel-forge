"""Locate the bundled Bun-served web editor.

The editor travels inside the wheel under ``voxel_forge/editor`` (see the
``force-include`` rules in ``pyproject.toml``) and lives in the top-level
``editor/`` directory in a repository checkout. Resolution goes through
:mod:`importlib.resources` first so the same code path works from both
layouts, mirroring simulacat's ``js_root`` pattern.

Examples
--------
Resolve the editor package root for ``bun install``::

    from voxel_forge.editor_runtime import editor_package_root

    root = editor_package_root()  # directory containing package.json
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path


class EditorRuntimeError(RuntimeError):
    """Raised when the bundled editor cannot be located or run."""


def editor_entrypoint() -> Path:
    """Return the path to the editor's Bun entry point script.

    Returns
    -------
    Path
        Absolute path to ``serve.ts``. The packaged location inside the
        installed wheel is preferred; a repository checkout is the
        fallback. The packaged candidate is returned even when absent so
        callers can produce a precise diagnostic.

    Examples
    --------
    >>> editor_entrypoint().name
    'serve.ts'
    """
    package_root = resources.files("voxel_forge")
    packaged = Path(str(package_root.joinpath("editor").joinpath("serve.ts")))
    checkout = Path(__file__).resolve().parents[2] / "editor" / "serve.ts"

    for candidate in (packaged, checkout):
        if candidate.is_file():
            return candidate

    return packaged


def editor_package_root() -> Path:
    """Return the directory containing the editor's ``package.json``.

    This is the JavaScript dependency root used for ``bun install`` in
    both editable-checkout and installed-wheel layouts.

    Returns
    -------
    Path
        Absolute path to the directory containing ``package.json``.

    Raises
    ------
    EditorRuntimeError
        If no ``package.json`` can be found next to the editor
        entry point.

    Examples
    --------
    >>> (editor_package_root() / "package.json").is_file()
    True
    """
    entrypoint = editor_entrypoint()
    candidate = entrypoint.parent

    if (candidate / "package.json").is_file():
        return candidate

    msg = f"Unable to locate the editor package.json next to {entrypoint}"
    raise EditorRuntimeError(msg)
