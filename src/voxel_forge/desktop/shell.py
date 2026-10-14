"""Platform shell helpers shared by the desktop widgets."""

from __future__ import annotations

import contextlib
import subprocess  # ruff: ignore[suspicious-subprocess-import]  # Needed to hand a folder to the platform shell.
import typing as typ

if typ.TYPE_CHECKING:
    from pathlib import Path


def open_folder(path: Path) -> None:
    """Reveal a directory in the platform file browser.

    Parameters
    ----------
    path
        Directory to show. A failure to launch the browser is ignored so
        that it never interrupts an editing session.
    """
    with contextlib.suppress(OSError):
        subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true]  # Fixed argument vector, never a shell string.
            ["explorer", str(path)],  # ruff: ignore[start-process-with-partial-path]  # Resolved from the system PATH.
            check=False,
        )
