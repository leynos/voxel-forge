"""Lifecycle diagnostics shared by the MCP server and the editor bridge.

Both components announce state transitions on standard error, because standard
output carries MCP protocol data. The announcements share one grammar — a
source, an ``operation`` name, then ordered ``key=value`` fields — and three
guides under ``docs/`` quote the exact strings, so the rendering lives here
rather than at each call site. One renderer is what keeps the field order, the
separator, and the stream consistent with what those guides promise.

This is not a general-purpose logger. Free-form failures keep their own
messages; only state transitions pass through :func:`emit_lifecycle`.
"""

from __future__ import annotations

import sys


def emit_lifecycle(source: str, operation: str, **fields: str) -> None:
    """Write one ``VoxelForge <source>: operation=<operation> <fields>`` line.

    ``fields`` render in the order given, so the caller controls a field order
    that both a log scraper and the documentation depend on. Values are
    interpolated verbatim: pass a class name or a label from a closed set, never
    an exception message, which may carry data the log should not hold.

    Parameters
    ----------
    source : str
        The component reporting, such as ``"server"`` or ``"bridge"``.
    operation : str
        The transition being reported, such as ``"bridge_start"``.
    **fields : str
        Ordered ``key=value`` fields describing that transition.

    Examples
    --------
    Report an on-demand bridge start; the line goes to standard error::

        emit_lifecycle("server", "bridge_start", trigger="launch_editor")
        # VoxelForge server: operation=bridge_start trigger=launch_editor
    """
    parts = [f"operation={operation}", *(f"{k}={v}" for k, v in fields.items())]
    print(f"VoxelForge {source}: {' '.join(parts)}", file=sys.stderr)
