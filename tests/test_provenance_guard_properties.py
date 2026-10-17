"""Property-based contract for the provenance guard's clause bracket.

``test_provenance_claims.py`` pins the guard with named examples: the shipped
overclaim must be caught, the project's own claim must not be. Those examples
say the guard works on the cases we thought of. This module asks the different
question of whether the *rule* behind it holds across the layout variations a
future edit could produce -- a reflowed blockquote, a separator moved, a link
nested deeper in the paragraph, an indented quote.

The property is about the separator, because that is the whole of the rule.
``_linked_passage`` walks outward from a link and stops at a bare ``>`` line,
which is what distinguishes the project's authorship claim from the
audit-describing paragraph. Two things must hold for any layout built that way:
an overclaim on the link's side of the separator is caught, and the project's
claim on the other side is not. Generating the layouts rather than listing them
is what makes a future change to the stopping rule show up here instead of in a
README.

Run with ``uv run pytest -q``. The generator stays close to real Markdown --
clauses are drawn from the real phrasings and only their placement varies -- so
a failure is a layout the guard mishandles, not a random string.
"""

from __future__ import annotations

import typing as typ

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from test_provenance_claims import _provenance_overclaim_offenders

if typ.TYPE_CHECKING:
    from pathlib import Path

# Every generated case writes the same body to both READMEs, so the guard scans
# the layout under test twice rather than once against a fixed mirror. The Thai
# file is not the subject here: this module varies *structure*, and the mirror
# rule (that both languages are scanned) is pinned by the example tests.
_ENGLISH = "README.md"

# The audit-describing clause that carries the overclaim, and the project claim
# that must never be reported. Drawn from the real phrasings, so a generated
# layout is one a README edit could actually produce.
_OVERCLAIM_CLAUSE = (
    "showing VoxelForge carries no Goxel C source, and the limits of it."
)
_PROJECT_CLAUSE = (
    "VoxelForge is an independent, MCP-first implementation that carries no "
    "Goxel C source."
)

_LINK = "[docs/provenance.md](docs/provenance.md)"

# A bare ``>`` is a blockquote paragraph break, which is the boundary the guard
# must respect. An indented variant is generated too, because the guard strips
# leading whitespace before testing for the marker. The prose line carries its
# own marker: it is *continuation* of the quote, and a line without one would
# end the passage outright rather than pad it.
_SEPARATOR = ">"
_PROSE = "> Further prose that describes neither claim."

# Quoted settings: every test here takes ``tmp_path``, which Hypothesis does not
# reset between generated examples. The bodies are fully rewritten each time, so
# reuse is what we want rather than a hazard.
#
# The deadline is off because each example writes two files and re-scans them:
# the per-example cost is dominated by filesystem latency, which varies with
# whatever else the machine is doing. A wall-clock threshold here would fail on
# a busy host and pass on an idle one without the guard's behaviour changing,
# so it would report load rather than a defect. The properties still bound
# their own work -- 200 examples, each a full guard run.
_SETTINGS = settings(
    max_examples=200,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)


def _write_pair(root: Path, blocks: list[str]) -> None:
    """Write one body to both README paths so the guard sees a complete pair."""
    body = "\n".join(blocks) + "\n"
    for name in (_ENGLISH, "README.th.md"):
        (root / name).write_text(f"# VoxelForge\n\n{body}", encoding="utf-8")


def _assert_guard_is_silent(root: Path, blocks: list[str], why: str) -> None:
    """Write a generated layout and assert the guard reports nothing.

    Three of the properties below differ only in the layout they generate; the
    procedure after generating it -- write the pair, run the guard, require no
    offenders -- is one step, so it lives here. ``why`` carries the explanation
    the failing layout needs, because the traceback will point at this call
    rather than at the test body that built the blocks.
    """
    _write_pair(root, blocks)
    offenders = _provenance_overclaim_offenders(root)
    assert not offenders, f"{why}:\n  " + "\n  ".join(offenders)


@_SETTINGS
@given(
    overclaim_first=st.booleans(),
    prose_between=st.integers(min_value=0, max_value=3),
    prose_after=st.integers(min_value=0, max_value=3),
)
def test_overclaim_never_separated_from_its_link_is_caught(
    tmp_path: Path,
    *,
    overclaim_first: bool,
    prose_between: int,
    prose_after: int,
) -> None:
    """An overclaim in the link's own paragraph must be reported.

    The clauses are placed on either side of the link but *within the same
    paragraph* -- no ``>`` separator between them -- and padding is added around
    and between them. Whichever order they appear in, and however much
    intervening prose there is, the two are one claim about the audit and the
    guard must read them as such.

    This is the direction a line-count window gets wrong in both ways: too short
    and it stops before the clause below the link, too long and it runs past
    into the next paragraph. Bracketing on the separator is what makes the
    answer independent of how many lines the padding happens to add.
    """
    paragraph = []
    if overclaim_first:
        paragraph.append(f"> {_OVERCLAIM_CLAUSE}")
        paragraph.extend([_PROSE] * prose_between)
        paragraph.append(f"> {_LINK}")
    else:
        paragraph.append(f"> {_LINK}")
        paragraph.extend([_PROSE] * prose_between)
        paragraph.append(f"> {_OVERCLAIM_CLAUSE}")
    paragraph.extend([_PROSE] * prose_after)

    _write_pair(tmp_path, paragraph)

    offenders = _provenance_overclaim_offenders(tmp_path)

    assert any(_ENGLISH in offender for offender in offenders), (
        "an overclaim left in the link's own blockquote paragraph escaped the "
        "guard; the clauses are one claim, so their order and the padding "
        "between them must not change the verdict"
    )


@_SETTINGS
@given(
    prose_before=st.integers(min_value=0, max_value=3),
    prose_after=st.integers(min_value=0, max_value=3),
    indent=st.sampled_from(["", " ", "  ", "\t"]),
)
def test_project_claim_across_a_separator_is_never_reported(
    tmp_path: Path,
    prose_before: int,
    prose_after: int,
    indent: str,
) -> None:
    """The project's claim, separated from the link, must not be reported.

    The authorship claim sits above a bare ``>`` and the audit-describing
    paragraph below it. That separator is the only thing distinguishing them,
    so it is the one input that must change the guard's answer -- and padding
    the paragraphs must not defeat it.

    The separator is generated with leading whitespace as well, because the
    guard decides what a separator is by stripping the line first. A rule that
    matched only a column-zero ``>`` would report the project's claim as soon as
    an edit indented the blockquote.

    Without this direction the property would be satisfiable by a guard that
    reported everything, which would fail on the shipped READMEs the moment it
    ran.
    """
    blocks = [_PROSE] * prose_before
    blocks.append(f"> {_PROJECT_CLAUSE}")
    blocks.append(f"{indent}{_SEPARATOR}")
    blocks.append(f"> {_LINK} records the source-history audit, and its limits.")
    blocks.extend([_PROSE] * prose_after)

    _assert_guard_is_silent(
        tmp_path,
        blocks,
        "the project's authorship claim was reported as an overclaim; it sits "
        "across a separator from the link, and the separator is the rule that "
        "protects it",
    )


@_SETTINGS
@given(separators_between=st.integers(min_value=1, max_value=3))
def test_project_claim_survives_repeated_separators(
    tmp_path: Path, separators_between: int
) -> None:
    """Extra separators between the claims must not pull them together.

    A Markdown blockquote allows a run of bare ``>`` lines, and a reflow can
    leave more than one. Each is a paragraph break, so the claims stay distinct
    however many appear; a guard that treated a run as a single break with
    different bracketing would report the project claim here.
    """
    blocks = [
        f"> {_PROJECT_CLAUSE}",
        *[_SEPARATOR] * separators_between,
        f"> {_LINK} records the source-history audit, and its limits.",
    ]

    _assert_guard_is_silent(
        tmp_path,
        blocks,
        "a run of separators was not treated as a paragraph break, so the "
        "project's claim was reported",
    )


@_SETTINGS
@given(blank_lines=st.integers(min_value=1, max_value=2))
def test_non_blockquote_line_ends_the_scan(tmp_path: Path, blank_lines: int) -> None:
    """Prose outside the blockquote must bound the passage.

    The guard reads outward from the link while the lines are blockquote lines,
    so a non-quote line ends the passage. That matters for the overclaim case
    too: a clause outside the quote is a different paragraph that the guard is
    right not to read as describing the audit. This pins the outward bound as a
    bound rather than as an accident of the shipped layout.
    """
    blocks = [
        f"> {_LINK} records the source-history audit, and its limits.",
        *[""] * blank_lines,
        f"Prose outside the quote. {_OVERCLAIM_CLAUSE}",
    ]

    _assert_guard_is_silent(
        tmp_path,
        blocks,
        "the guard read past the end of the blockquote into unrelated prose",
    )
