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


def main() -> int:
    """Launch the desktop application, degrading gracefully without PySide6.

    Returns ``0`` on a clean exit and ``1`` when the ``desktop`` extra is
    not installed. Import errors unrelated to the optional GUI stack are
    re-raised so genuine defects still surface as tracebacks.
    """
    try:
        from .app import main as run_desktop_app
    except ImportError as exc:
        missing = getattr(exc, "name", None) or ""
        if not missing.startswith(("PySide6", "shiboken")):
            raise
        print(_EXTRA_HINT.format(missing=missing), file=sys.stderr)
        return 1
    run_desktop_app()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
