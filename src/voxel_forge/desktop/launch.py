"""Entry point for the ``voxel-forge`` desktop command.

The desktop application depends on PySide6, which is an optional
``desktop`` extra. An installed tool exposes the ``voxel-forge`` command
whether or not the extra is present, so the import failure must be
translated into an actionable message rather than a traceback.
"""

from __future__ import annotations

import sys

_EXTRA_HINT = (
    "The VoxelForge desktop application requires the optional 'desktop' extra"
    " (missing dependency: {missing}).\n"
    "Install it with one of:\n"
    "  uv tool install 'voxel-forge[desktop] @ git+https://github.com/leynos/voxel-forge'\n"
    "  uv sync --extra desktop  (from a checkout)"
)

# Top-level distributions that only the `desktop` extra installs. CPython
# reports the leaf module name for an extension that fails to load, so the
# prefix match has to tolerate dotted names such as ``PySide6.QtCore``.
_DESKTOP_DISTRIBUTIONS = ("PySide6", "shiboken")


def _names_missing_desktop_extra(exc: ImportError) -> bool:
    """Report whether ``exc`` is the optional GUI stack failing to import."""
    # A plain absent package arrives as ``name='PySide6'``, which means the
    # extra was not installed. A PySide6 that *is* installed but whose shared
    # libraries cannot load arrives as the extension's leaf name instead
    # (``name='QtCore'``, with ``path`` naming the ``.so``), so it stays
    # unrelated here and the traceback names the missing native library rather
    # than misdirecting the user to an extra they already have.
    missing = getattr(exc, "name", None) or ""
    return missing.startswith(_DESKTOP_DISTRIBUTIONS)


def main() -> int:
    """Launch the desktop application, degrading gracefully without PySide6.

    Only the failure of the optional GUI stack is handled here; on the normal
    path this function does not return, because the application terminates the
    process itself through ``sys.exit(app.exec())`` once its window closes.

    Returns
    -------
    int
        ``1`` when the ``desktop`` extra is not installed, after an actionable
        message has been written to standard error. Import errors unrelated to
        the optional GUI stack are re-raised so genuine defects still surface
        as tracebacks.
    """
    try:
        from .app import main as run_desktop_app
    except ImportError as exc:
        if not _names_missing_desktop_extra(exc):
            raise
        missing = getattr(exc, "name", None) or ""
        print(_EXTRA_HINT.format(missing=missing), file=sys.stderr)
        return 1
    run_desktop_app()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
