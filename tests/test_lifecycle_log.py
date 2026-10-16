"""Contract tests for the shared lifecycle diagnostic renderer.

The server and the bridge both announce transitions on stderr, and three guides
under ``docs/`` quote the resulting lines verbatim. Those quotes are the
contract: a scraper matching them must keep matching after any refactor, so the
rendering is pinned here rather than left to two hand-written f-strings that
could drift apart.

A second contract sits underneath the first: one call renders one line. The
examples pin the three lines the guides quote; the properties and the terminator
table below cover the values a future caller might pass.
"""

from __future__ import annotations

import contextlib
import io

import pytest
from hypothesis import given
from hypothesis import strategies as st

from voxel_forge.lifecycle_log import emit_lifecycle

# Every character ``str.splitlines`` treats as a line boundary, spelled out here
# rather than imported from the renderer. The duplication is deliberate: this
# table is the oracle the tests judge the renderer against, so reading it from
# the module under test would let a narrowed guard weaken its own check.
_LINE_BREAKS = {
    "\n": "newline",
    "\r": "carriage-return",
    "\x0b": "vertical-tab",
    "\x0c": "form-feed",
    "\x1c": "file-separator",
    "\x1d": "group-separator",
    "\x1e": "record-separator",
    "\x85": "next-line",
    "\u2028": "line-separator",
    "\u2029": "paragraph-separator",
}


def _is_single_line(text: str) -> bool:
    r"""Report whether ``text`` carries no terminator the renderer must refuse.

    Asking only for ``"\\n" not in text`` would offer the generator a form feed
    or a Unicode line separator: the renderer refuses those rightly, so the
    property would report a refused call as a rendering failure. Counting
    ``splitlines`` parts would not serve either — a lone terminator gives
    ``[""]``, one part — so the predicate asks about the characters directly.
    """
    return not set(_LINE_BREAKS) & set(text)


# A field value the renderer must accept: no line terminator inside it, so one
# call can still be one line.
_SINGLE_LINE = st.text(max_size=40).filter(_is_single_line)

# Names ``emit_lifecycle`` binds itself. A field so named would be swallowed by
# the signature rather than reaching ``**fields``, which is a caller error the
# renderer cannot see; generating one would fail the test with a confusing
# TypeError instead of exercising the rendering.
_RESERVED = frozenset({"source", "operation"})
_FIELD_NAME = _SINGLE_LINE.filter(lambda name: name not in _RESERVED)


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


@given(fields=st.dictionaries(_FIELD_NAME, _SINGLE_LINE, max_size=5))
def test_generated_fields_preserve_insertion_order_on_one_line(
    fields: dict[str, str],
) -> None:
    """Any terminator-free field set must render once, in the order it was given.

    The fixed examples above pin the three lines the guides quote. This is the
    broader promise underneath them: whatever a caller passes, field order is
    the call order and there is exactly one line, so a scraper that groups by
    ``operation`` cannot lose or duplicate a transition. Field names and values
    are drawn from the same space to keep the check honest about which side a
    stray separator could come from.

    The stream is redirected rather than taken from ``capsys``, because that
    fixture is function-scoped and Hypothesis does not reset it between
    generated inputs.
    """
    stream = io.StringIO()
    with contextlib.redirect_stderr(stream):
        emit_lifecycle("bridge", "bridge_state", **fields)

    rendered = stream.getvalue()
    lines = rendered.splitlines()
    assert len(lines) == 1, (
        f"one call with terminator-free fields must emit one line, got: {rendered!r}"
    )
    # Built here from the documented grammar rather than parsed back out of the
    # line: a generated key or value may itself contain a space or be empty, so
    # splitting the line on spaces would report a rendering fault where the line
    # is exactly right. The fields go through the same single-space join the
    # grammar describes, which is what makes the comparison order-sensitive —
    # sorted fields would produce a different string.
    parts = ["operation=bridge_state", *(f"{k}={v}" for k, v in fields.items())]
    expected = f"VoxelForge bridge: {' '.join(parts)}"
    assert lines[0] == expected, (
        f"the fields must render in insertion order, got: {rendered!r}"
    )


# Where the terminator sits in the value, as a template around it. The two
# positions are separate cases because they defeat different guards: a check for
# a terminator *before* the last character passes the trailing one, and a guard
# that counted ``splitlines`` parts would read the trailing one as a single line
# and wave it through.
_TERMINATOR_POSITIONS = {
    "embedded": "launch_editor{}x",
    "trailing": "launch_editor{}",
}


@pytest.mark.parametrize(
    "placement", _TERMINATOR_POSITIONS, ids=list(_TERMINATOR_POSITIONS)
)
@pytest.mark.parametrize("separator", _LINE_BREAKS, ids=list(_LINE_BREAKS.values()))
def test_a_value_carrying_a_line_terminator_is_refused(
    separator: str, placement: str, capsys: pytest.CaptureFixture[str]
) -> None:
    r"""A value carrying a line terminator must be refused, wherever it sits.

    Accepting one would let a call render as two lines, so a scraper counting
    ``bridge_start`` would overcount and a crafted value could forge a second
    transition. Every terminator ``str.splitlines`` breaks on is listed, not
    just the ASCII ones: a reader is what decides where a line ends, so a guard
    covering fewer of them than the reader would admit forged lines through the
    gap. Refusing is a deliberate contract, not defensive decoration — this
    renderer is the only place able to promise one call means one line.

    The trailing case earns its own row: ``"a\\n".splitlines()`` is ``["a"]``,
    one part, so only a character-membership guard refuses it. Counting split
    parts — the obvious test, and my own first attempt — writes a bare second
    line here.
    """
    value = _TERMINATOR_POSITIONS[placement].format(separator)
    with pytest.raises(ValueError, match="one line"):
        emit_lifecycle("server", "bridge_start", trigger=value)

    assert not capsys.readouterr().err, (
        "a refused report must not reach the diagnostic stream at all"
    )
