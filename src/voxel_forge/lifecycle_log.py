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

# Every character ``str.splitlines`` treats as a line boundary. The guard below
# tests membership rather than counting ``splitlines`` parts, because counting
# misses a *trailing* terminator: ``"a\n".splitlines()`` is ``["a"]``, yet
# printing it writes a bare second line. A guard narrower than the reader would
# admit exactly the values that prove it wrong.
_LINE_BREAKS = frozenset("\n\r\v\f\x1c\x1d\x1e\x85\u2028\u2029")


def emit_lifecycle(source: str, operation: str, **fields: str) -> None:
    r"""Write one ``VoxelForge <source>: operation=<operation> <fields>`` line.

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

    Raises
    ------
    ValueError
        If the rendered line would be read as more than one line. One call has
        to mean one line: a scraper counting ``bridge_start`` would otherwise
        read a single transition as several, and a value carrying a terminator
        could forge a whole second transition. Every call site passes a label
        from a closed set, so this guards a future caller rather than a case the
        current ones reach. The message names only ``operation``, itself a
        closed-set label, so a refused value is never echoed into a traceback.

    Notes
    -----
    The check covers every character ``str.splitlines`` treats as a boundary,
    not just ``"\n"`` and ``"\r"``: that method also breaks on vertical tab,
    form feed, ``\x1c``-``\x1e``, ``\x85``, and the Unicode line and paragraph
    separators. A guard narrower than the reader would admit exactly the values
    that prove it wrong.

    Examples
    --------
    Report an on-demand bridge start; the line goes to standard error::

        emit_lifecycle("server", "bridge_start", trigger="launch_editor")
        # VoxelForge server: operation=bridge_start trigger=launch_editor
    """
    parts = [f"operation={operation}", *(f"{k}={v}" for k, v in fields.items())]
    line = f"VoxelForge {source}: {' '.join(parts)}"
    if _LINE_BREAKS.intersection(line):
        msg = f"lifecycle operation {operation!r} must render on one line"
        raise ValueError(msg)
    print(line, file=sys.stderr)
