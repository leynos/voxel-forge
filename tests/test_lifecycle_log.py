"""Contract tests for the shared lifecycle diagnostic renderer.

The server and the bridge both announce transitions on stderr, and three guides
under ``docs/`` quote the resulting lines verbatim. Those quotes are the
contract: a scraper matching them must keep matching after any refactor, so the
rendering is pinned here rather than left to two hand-written f-strings that
could drift apart.
"""

from __future__ import annotations

import typing as typ

if typ.TYPE_CHECKING:
    import pytest

from voxel_forge.lifecycle_log import emit_lifecycle


def test_fields_render_in_the_order_given(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Field order must follow the call, not the alphabet.

    ``bridge_state`` reads before ``error_category`` because the state is the
    subject and the category qualifies it. An implementation that sorted the
    fields would still produce a parseable line, so only an order-sensitive
    assertion catches that regression.
    """
    emit_lifecycle(
        "bridge", "bridge_state", bridge_state="down", error_category="CancelledError"
    )

    captured = capsys.readouterr()
    assert (
        captured.err.strip()
        == "VoxelForge bridge: operation=bridge_state bridge_state=down "
        "error_category=CancelledError"
    ), f"the fields must render in call order, got: {captured.err!r}"


def test_the_line_goes_to_stderr_not_stdout(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Diagnostics must stay off stdout, which carries MCP protocol data.

    A lifecycle line written to stdout would corrupt the protocol stream, so the
    stream is asserted rather than assumed.
    """
    emit_lifecycle("server", "bridge_start", trigger="launch_editor")

    captured = capsys.readouterr()
    assert not captured.out, "the diagnostic must not reach the protocol stream"
    assert (
        captured.err.strip()
        == "VoxelForge server: operation=bridge_start trigger=launch_editor"
    ), f"the start must report itself on stderr, got: {captured.err!r}"


def test_one_line_per_call(capsys: pytest.CaptureFixture[str]) -> None:
    """Each report must be a single line, so a line-oriented scraper can read it.

    A newline inside a rendered value would split one transition across two
    lines and let a counter over ``bridge_start`` overcount. Values come from
    closed sets, but the renderer must not be the thing that assumes it.
    """
    emit_lifecycle(
        "server", "server_start", bridge_mode="eager", bridge_state="running"
    )

    captured = capsys.readouterr()
    assert len(captured.err.strip().splitlines()) == 1, (
        f"one call must emit one line, got: {captured.err!r}"
    )
