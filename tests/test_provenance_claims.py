"""Executable contract for what the READMEs may claim about the audit.

`docs/provenance.md` backs its authorship claim with a source-history audit and
states plainly what that audit does not establish. The summary of the document
-- the blockquote and the linked bullet in each README -- is what a reader acts
on, and it is prose that no test can check. What a test *can* check is the
string, and the defect this module guards against is a summary that credits the
audit with proving an absence it explicitly declines to infer.

Run with ``uv run pytest -q``. The guard is exercised in both directions: the
overclaim must be caught, and the project's own claim must not be.
"""

from __future__ import annotations

import typing as typ

import pytest
from readiness_helpers import REPOSITORY_ROOT

if typ.TYPE_CHECKING:
    from pathlib import Path

# Phrasings that credit an audit with *showing* the absence of Goxel C source,
# in either README language. The audit reports which suffixes and markers it
# searched for and found; absence of source is an inference it explicitly
# declines to draw, so prose claiming it demonstrated that is overclaiming.
_PROVENANCE_OVERCLAIMS = (
    "carries no Goxel",
    "no Goxel C",
    "ไม่มีซอร์สโค้ด",
    "ไม่พบซอร์สโค้ด",
)

# The bilingual pair AGENTS.md requires to be kept in step. Scanned as a pair
# because a claim corrected in one and left in the other survives review by
# being split across two files.
_README_MIRROR = ("README.md", "README.th.md")

# The project's own authorship claim, which the guard must leave alone: the
# subject is VoxelForge, not the audit. Both READMEs separate it from the
# blockquote that links the document with a bare ``>`` line, and that separator
# is what the scan stops at.
_PROJECT_CLAIM = (
    "> VoxelForge is an independent, MCP-first implementation that carries no\n"
    "> Goxel C source.\n"
    ">\n"
    "> [docs/provenance.md](docs/provenance.md) records the audit behind it.\n"
)

# The same words attached to the audit instead of the project. This is the
# defect the guard exists for, and it is what the READMEs said before the guard
# was added.
_AUDIT_OVERCLAIM = (
    "> [docs/provenance.md](docs/provenance.md) records the source-history audit\n"
    "> showing VoxelForge carries no Goxel C source, and the limits of it.\n"
)

# The same overclaim with its clauses transposed, so the claim precedes the
# link. A forward-only scan never reaches it, which is why it is a control of
# its own rather than a variant of the pair above: the direction was a hole in
# the guard, not a detail of how the wording was written.
_AUDIT_OVERCLAIM_ABOVE_LINK = (
    "> VoxelForge carries no Goxel C source, as\n"
    "> [docs/provenance.md](docs/provenance.md) shows.\n"
)

_THAI_MIRROR = {
    _PROJECT_CLAIM: (
        "> VoxelForge เป็น implementation อิสระที่ไม่มีซอร์สโค้ด C ของ Goxel\n"
        ">\n"
        "> [ที่มา](docs/provenance.md) บันทึกการตรวจสอบที่รองรับ\n"
    ),
    _AUDIT_OVERCLAIM: (
        "> [ที่มา](docs/provenance.md) บันทึกการตรวจสอบที่แสดงว่า VoxelForge\n"
        "> ไม่มีซอร์สโค้ด C ของ Goxel\n"
    ),
    _AUDIT_OVERCLAIM_ABOVE_LINK: (
        "> VoxelForge ไม่มีซอร์สโค้ด C ของ Goxel ดังที่\n> [ที่มา](docs/provenance.md) แสดง\n"
    ),
}


def _linked_passage(lines: list[str], index: int) -> str:
    """Return the text around ``lines[index]`` that describes the audit.

    The passage is bracketed rather than a fixed number of lines, because the
    two directions need different stopping rules and a line count gets both
    wrong.

    Forward, the passage runs to the end of the enclosing blockquote: the
    description continues beneath the link, and stopping early would let an
    overclaim written below it escape. Measured against the shipped READMEs, a
    forward window is clean out to eighty lines, so there is no risk in reading
    the whole block; the only reason not to is that a link at the bottom of a
    long blockquote would pull unrelated prose into scope.

    Backward, it stops at a bare ``>`` line, or at the first non-blockquote
    line. That separator is the structural boundary in both READMEs: the
    project's authorship claim sits above it and the audit-describing paragraph
    below, so stopping there is what keeps the guard from flagging the claim it
    exists to protect. The separator is used rather than a line count because it
    is what actually separates the two claims -- a count is a guess about
    layout, and the shipped layout already puts them four lines apart.

    Backward really is scanned. An overclaim can be written *above* its own
    link, as in "VoxelForge carries no Goxel C source, as
    [the audit](...) shows", which credits the audit just as plainly as the
    below-link form and is the case a forward-only window misses entirely.

    A residual false positive remains, and it is accepted rather than
    overlooked: delete the bare ``>`` separator so the authorship claim joins
    the link's paragraph and the guard reports it. That edit makes the two
    sentences one claim, and which of them the audit is said to support stops
    being recoverable from the text, so failing is the safer reading.
    """

    def is_blockquote(i: int) -> bool:
        return 0 <= i < len(lines) and lines[i].lstrip().startswith(">")

    def is_separator(i: int) -> bool:
        return lines[i].strip() == ">"

    start = end = index
    while start - 1 >= 0 and is_blockquote(start - 1) and not is_separator(start - 1):
        start -= 1
    while end + 1 < len(lines) and is_blockquote(end + 1):
        end += 1
    return "\n".join(lines[start : end + 1])


def _provenance_overclaim_offenders(root: Path) -> list[str]:
    """Find passages that credit the provenance audit with proving an absence.

    Scanned as a mirrored pair, because a claim corrected in one README and
    left in the other is a defect that survives review by being split across
    two files. A missing mirror is reported as an offender rather than skipped:
    the pair is what AGENTS.md requires, so an absent ``README.th.md`` means
    the guard is inspecting half the surface it claims to cover, and skipping
    it would report the same clean result as reading it.

    Only passages that link to ``provenance.md`` are inspected, and only while
    they describe that document -- the linked bullet in each README's
    documentation list, and the blockquote near the top of each. The project's
    own claim that VoxelForge "carries no Goxel C source" is a deliberate
    statement about the code, and it is the claim the audit supports. What must
    not appear is the same phrasing attached to the audit, which asserts a
    stronger thing: that the audit demonstrated the absence rather than
    supporting it. Scoping to audit-describing passages is what separates the
    two, so a whole-file search for "no Goxel" would fail on the claim it is
    meant to protect.

    The passage is bracketed on structure rather than on a line count, which is
    what separates the two claims: the project's authorship claim and the
    audit-describing paragraph are different blockquote paragraphs, divided by a
    bare ``>`` line. Reading to that separator is what keeps the guard from
    flagging the claim it exists to protect, and reading *across* it forward is
    what stops a description running on beneath the link from escaping.
    ``_linked_passage`` carries the bracketing rules and the false positive this
    still accepts.

    The ``roadmap`` and ``fork-and-interface-boundary`` passages that mention
    the audit are out of scope: the first is a planning record of work, and the
    second only points at where provenance is recorded rather than
    characterising what the audit established.

    Parameters
    ----------
    root : Path
        Repository root to scan.

    Returns
    -------
    list[str]
        ``path:line: text`` for each overclaiming passage, empty when none
        remain.
    """
    offenders: list[str] = []
    for name in _README_MIRROR:
        path = root / name
        if not path.is_file():
            offenders.append(f"{name}: missing (the README pair is mirrored)")
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        for index, line in enumerate(lines):
            if "provenance.md" not in line:
                continue
            passage = _linked_passage(lines, index)
            offenders.extend(
                f"{name}:{index + 1}: {phrase!r}"
                for phrase in _PROVENANCE_OVERCLAIMS
                if phrase in passage
            )
    return offenders


def test_provenance_audit_is_not_credited_with_proving_absence() -> None:
    """The audit must be described as searching, not as proving absence.

    The claim was narrowed five times during review, each pass removing a
    narrower thing the audit does not establish, until the document reported
    only the suffixes and markers it found. The READMEs were not part of those
    passes, so both still described the audit as showing that VoxelForge
    carries no Goxel C source -- the exact overclaim that had just been removed
    from the document the sentence points at. A reader following the link would
    find the document disclaiming what the link promised.

    Guarding the wording rather than the linked file is the point: the audit
    itself is prose no test can check, but the summary claim is a string, and
    it is the summary readers act on.
    """
    offenders = _provenance_overclaim_offenders(REPOSITORY_ROOT)

    assert not offenders, (
        "these passages credit the provenance audit with demonstrating an "
        "absence it does not establish:\n  " + "\n  ".join(offenders)
    )


def _write_readme_pair(root: Path, body: str) -> None:
    """Write a mirrored README pair carrying ``body`` in both languages."""
    (root / "README.md").write_text(f"# VoxelForge\n\n{body}", encoding="utf-8")
    (root / "README.th.md").write_text(
        f"# VoxelForge\n\n{_THAI_MIRROR[body]}", encoding="utf-8"
    )


def test_the_guard_catches_the_overclaim_it_was_written_for(
    tmp_path: Path,
) -> None:
    """Restoring the old wording must fail, not pass quietly.

    The guard is only worth having if it still fires. Rerunning it against a
    tree carrying the pre-fix sentence is the negative control: it exercises
    the detector rather than the READMEs, so a future narrowing of the phrases
    or the window that quietly stops catching the defect shows up here instead
    of in production.
    """
    _write_readme_pair(tmp_path, _AUDIT_OVERCLAIM)

    offenders = _provenance_overclaim_offenders(tmp_path)

    assert offenders, (
        "the guard no longer catches the overclaim it was written for; the "
        "restored wording passed a scan that should have rejected it"
    )
    assert any("README.md" in offender for offender in offenders), (
        "the English README's overclaim must be reported, not only the mirror"
    )


def test_the_guard_leaves_the_project_claim_alone(tmp_path: Path) -> None:
    """The claim the audit supports must not be reported as an overclaim.

    This is the false-positive control, and it is the one that constrains the
    scan window. Both READMEs carry the project's attribution claim in the
    blockquote directly above the link, so a guard that reads backwards from
    the link flags correct prose. Failing here means the guard has started
    rejecting the sentence it exists to protect.
    """
    _write_readme_pair(tmp_path, _PROJECT_CLAIM)

    offenders = _provenance_overclaim_offenders(tmp_path)

    assert not offenders, (
        "the project's own authorship claim was reported as an overclaim, "
        "which means the scan is reading text that describes the code rather "
        "than text that describes the audit:\n  " + "\n  ".join(offenders)
    )


def test_the_guard_catches_an_overclaim_above_its_own_link(tmp_path: Path) -> None:
    """An overclaim written above the link must fail, not slip past.

    The scan reads backwards as well as forwards, and this is the control that
    holds that direction in place. The wording below is the overclaim with its
    clauses swapped -- the claim first, the link second -- which credits the
    audit with demonstrating the absence exactly as the below-link form does. A
    forward-only window, which is what this guard once used, misses it
    completely: it never reaches text that precedes the link.

    Both directions are worth scanning because the defect is about which subject
    the phrase attaches to, and that attachment does not depend on which side of
    the link it lands. Only the *separator* rule can tell the project's claim
    from the audit's, which is why the guard stops there rather than on a line
    count.
    """
    _write_readme_pair(tmp_path, _AUDIT_OVERCLAIM_ABOVE_LINK)

    offenders = _provenance_overclaim_offenders(tmp_path)

    assert any("README.md" in offender for offender in offenders), (
        "the guard missed an overclaim written above its own link; a "
        "forward-only window cannot reach text that precedes the link"
    )


def test_a_missing_mirror_is_reported_rather_than_skipped(tmp_path: Path) -> None:
    """An absent ``README.th.md`` must fail, not silently halve the scan.

    The pair is what keeps one language from drifting, so a guard that skips an
    absent mirror reports the same clean result whether it read both files or
    only one. Deleting the Thai README would otherwise disable half the check
    while leaving the suite green.
    """
    _write_readme_pair(tmp_path, _PROJECT_CLAIM)
    (tmp_path / "README.th.md").unlink()

    offenders = _provenance_overclaim_offenders(tmp_path)

    assert any("README.th.md" in offender for offender in offenders), (
        "an absent mirror must be reported; it is unscanned, not clean"
    )


@pytest.mark.parametrize("name", _README_MIRROR)
def test_the_repository_carries_both_readme_languages(name: str) -> None:
    """The mirrored pair must exist here, or the guard above is half a guard."""
    assert (REPOSITORY_ROOT / name).is_file(), (
        f"{name} is missing; AGENTS.md requires the English and Thai READMEs to "
        "be maintained together"
    )
