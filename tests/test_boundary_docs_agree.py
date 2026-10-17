"""Executable contract for the guides' agreement about the consumer boundary.

This branch added the consumer-boundary section to the developers guide and
the boundary document. Both said VoxelForge is "never a library" and that a
consumer "vendors no VoxelForge code", while the users guide went on
documenting `voxel_forge.vox_io.export_obj` and
`voxel_forge.export_roblox.to_luau_merged` as supported Python entry points.

Read together, a contributor could conclude the Python helpers were
unsupported, because the qualification -- that "never a library" is about
co-owned code rather than about importing the package -- was present in
neither place. The contradiction was created by the new section, not inherited
with the old text, and nothing in the suite could see it: each document is
internally consistent, and only the set of them is not.

That is the defect this module guards. It is a *cross-document* check, which
is why it does not live beside the other documentation tests: those read one
file and assert what it says, while this one reads several and asserts that
they do not say incompatible things.

Run with ``uv run pytest -q``.
"""

from __future__ import annotations

import pytest
from readiness_helpers import REPOSITORY_ROOT

# The documents that make a claim about the consumer boundary. The boundary
# document is the normative statement, the developers guide restates the part
# that constrains a change, the users guide is where the Python helpers are
# documented, and the migration guide points at them.
_BOUNDARY_DOCUMENTS = (
    "docs/fork-and-interface-boundary.md",
    "docs/developers-guide.md",
    "docs/users-guide.md",
    "docs/migration-0.3.md",
)

# The phrase each boundary document opens its prohibition with, so a rename
# that left the qualification behind fails here rather than silently detaching
# the explanation from the rule it explains.
_PROHIBITION_ANCHORS = {
    "docs/fork-and-interface-boundary.md": "out of scope",
    "docs/developers-guide.md": "out of scope",
}

# The qualification, stated in the words the guides actually use. A document
# that forbids the shared-library direction must also say which direction is
# forbidden, and that importing the installed package is not it.
#
# Each phrase asserts the permission rather than mentioning the act. The check
# below is a substring search, so a phrase naming the *act* is satisfied by a
# sentence forbidding it -- "importing the package" occurs in "Never consider
# importing the package" verbatim -- and a bare "import" occurs in
# "unimportable", the opposite claim. Each phrase here therefore carries the
# word that makes it a permission, and it is the permission a negation cannot
# repeat unaltered.
#
# Naming the import is what makes a phrase safe here, and "is allowed" alone
# fails that twice over: it matches "Vendoring source is allowed", a sentence
# about the *opposite* direction with no import in it, and it matches
# "Importing the installed package is forbidden; vendoring source is allowed",
# which permits the shared-library direction while forbidding the import. A
# phrase admitted here must contain a word for the act. The guard test below
# enforces that of the whole list rather than trusting this comment.
_IMPORT_NOUNS = ("import", "in-process")

_IMPORT_IS_SUPPORTED = (
    "can be imported",
    "may be imported",
    "importing the installed package is allowed",
)

# The documents that state the permission in their own words. The boundary
# contract binds every document in the set, but only these three assert the
# permission; the migration guide reaches it by link, so it is bound by the
# prohibition check below and not by this one. Splitting the requirement this
# way is what keeps the check honest -- widening the phrase list to make a
# merely-linking document pass would have meant accepting a bare mention, which
# is the weakness this test exists to avoid.
_DOCUMENTS_STATING_IMPORT_IS_SUPPORTED = {
    "docs/fork-and-interface-boundary.md": (
        "it is where the boundary contract itself is stated, so it must "
        "disclose that the contract does not forbid the import"
    ),
    "docs/developers-guide.md": (
        "it is where a contributor reads which direction the rule forbids, so "
        "it must say that importing the package is not the forbidden one"
    ),
    "docs/users-guide.md": (
        "it is where a consumer reads that the Python helpers are a supported "
        "in-process API"
    ),
}

# What each downstream document must keep naming, keyed by the document. The
# users guide is where the helpers are documented, so it must name them and
# label them supported; the migration guide reaches them by link, so it must
# keep both the link and the names its argument changes are about. Table-driven
# so each document's requirement fails on its own, rather than the two being
# one test that reports whichever it happened to reach first.
_DOCUMENT_HELPER_CLAIMS = {
    "docs/users-guide.md": (
        "export_obj",
        "to_luau_merged",
        "supported in-process API",
    ),
    "docs/migration-0.3.md": (
        "users-guide.md",
        "export_obj",
        "to_luau_merged",
    ),
}

# Why each document needs the phrases above, so a failure says what the
# document is for rather than only what went missing from it.
_DOCUMENT_ROLES = {
    "docs/users-guide.md": (
        "it is where a consumer reads that the Python helpers are a supported "
        "in-process API"
    ),
    "docs/migration-0.3.md": (
        "it is where an existing integration is told which helpers are "
        "changing, and it reaches them through the users guide"
    ),
}


def _read(relative: str) -> str:
    """Return one document's text, failing loudly if it is missing."""
    path = REPOSITORY_ROOT / relative
    assert path.is_file(), f"{relative} is missing from the documentation set"
    return path.read_text(encoding="utf-8")


def test_the_requirement_tables_cover_every_boundary_document() -> None:
    """Every boundary document must carry a requirement, and every key a file.

    The tables below are the specification, and a document missing from all of
    them is one no test reads: adding a guide to ``_BOUNDARY_DOCUMENTS`` and
    stopping there would look like coverage while checking nothing, which is
    the failure mode this module exists to catch, one level up. The converse
    matters as much -- a key naming a file that is not in the master list would
    silently widen the set the module claims to cover.

    The two directions are asserted separately so a failure says which one
    broke rather than only that the sets differ.

    Note this checks only that *some* requirement names each document, not that
    the right one does. ``docs/migration-0.3.md`` naming the helpers is checked
    here, but whether it carries the prohibition is not -- and must not be, since
    it is not a document the rule is stated in.
    """
    checked = (
        set(_DOCUMENTS_STATING_IMPORT_IS_SUPPORTED)
        | set(_PROHIBITION_ANCHORS)
        | set(_DOCUMENT_HELPER_CLAIMS)
    )
    declared = set(_BOUNDARY_DOCUMENTS)

    assert not declared - checked, (
        "these documents are declared boundary documents but no requirement "
        f"table covers them, so nothing reads them: {sorted(declared - checked)}"
    )
    assert not checked - declared, (
        "these documents are checked but missing from _BOUNDARY_DOCUMENTS, so "
        f"the module under-reports what it covers: {sorted(checked - declared)}"
    )


@pytest.mark.parametrize(
    ("relative", "role"),
    sorted(_DOCUMENTS_STATING_IMPORT_IS_SUPPORTED.items()),
)
def test_each_boundary_document_states_the_python_helpers_are_supported(
    relative: str, role: str
) -> None:
    """Every document that states the permission must state it affirmatively.

    Asserting this per document rather than on the set as a whole is the point:
    the defect was one document forbidding what another documented, and a
    check that concatenated all four would pass while any single one
    contradicted the rest.

    Only the documents that state the permission are checked. The migration
    guide, which reaches the helpers by link, is not unguarded for it -- but the
    check that covers it is the helper-name one, not the prohibition one: that
    one names only the two documents that carry the rule. Widening this phrase
    list until a merely-linking document passed is the tempting shortcut and it
    is the wrong one: the only wording a linking document could satisfy it with
    is a bare mention, which is precisely the weakness
    ``test_the_import_guard_rejects_a_negated_document`` exists to catch.

    ``role`` says what the document is *for*, so a failure names the reader who
    is being misled rather than only the phrase that went missing.
    """
    assert _states_importing_is_supported(_read(relative)), (
        f"{relative} describes the consumer boundary without saying that "
        f"importing the installed package is supported, and {role}; a reader "
        "of this document alone can conclude the Python helpers are out of "
        "bounds"
    )


def _states_importing_is_supported(text: str) -> bool:
    """Return whether ``text`` says the installed package may be imported.

    Newlines and runs of spaces are collapsed first. These documents are
    wrapped at 80 columns, so a phrase can straddle a line break -- and a
    guard that silently missed one would report a document as lacking a
    statement it makes, which is the kind of false failure that gets a check
    loosened rather than fixed.
    """
    flattened = " ".join(text.lower().split())
    return any(term in flattened for term in _IMPORT_IS_SUPPORTED)


@pytest.mark.parametrize(
    "negated",
    [
        "The consumer must never import the installed package.",
        "Importing the package is not supported.",
        "The contribution boundary makes the package unimportable.",
        # The permission this module is *not* looking for. Vendoring and
        # co-owning types are the shared-library direction the contract rules
        # out, so a document could grant one of those and read as satisfying a
        # check whose subject is the opposite permission -- and the old
        # "is allowed" term did satisfy it, twice, on sentences that never
        # mention an import.
        "Vendoring VoxelForge source is allowed.",
        "Importing the installed package is forbidden; vendoring source is allowed.",
    ],
)
def test_the_import_guard_rejects_a_negated_document(negated: str) -> None:
    """Text that does not grant this permission must fail the check.

    The guard above is a substring search, so what it accepts is only as good
    as the phrases it searches for. Most cases here are wording a document
    could plausibly use to *forbid* the import. The third is the sharpest of
    those: it contains the substring ``import``, which is why the guard cannot
    search for that word alone -- doing so would have let a document forbidding
    the import satisfy a check meant to find one permitting it, which is
    exactly the defect the boundary tests exist to catch, reintroduced inside
    the test that catches it.

    The last two are a different failure and the reason this test is not only
    about negations: text can be affirmative and still be about the wrong
    permission. ``Vendoring VoxelForge source is allowed`` grants the direction
    the contract forbids, and the second case grants it while explicitly
    forbidding the import. Both passed before the phrase naming the import
    replaced the bare ``is allowed``.
    """
    assert not _states_importing_is_supported(negated), (
        f"the guard accepted text that does not grant the import permission: "
        f"{negated!r}. Reword _IMPORT_IS_SUPPORTED as clauses only a statement "
        "about importing the installed package can contain"
    )


def test_every_accepted_phrase_names_the_import_it_grants() -> None:
    """Each phrase must mention the act, not merely that something is permitted.

    A phrase with no word for the import is satisfied by any permission
    sentence in the document, including one granting vendoring or co-ownership.
    That is not hypothetical -- ``is allowed`` was in this list and matched
    both counterexamples the guard test above now carries -- so the check is
    structural rather than a reading of the current three entries: whatever is
    added here later has to name the act too.

    The whole phrase is checked, not just its first word, because the failure
    mode is a phrase that is *only* a permission: a longer clause like
    ``importing the installed package is allowed`` carries the noun and passes
    on its own merits, which is exactly the shape wanted.
    """
    unnamed = [
        phrase
        for phrase in _IMPORT_IS_SUPPORTED
        if not any(noun in phrase for noun in _IMPORT_NOUNS)
    ]

    assert not unnamed, (
        f"these phrases grant a permission without naming the import, so text "
        f"about a different permitted direction would satisfy them: {unnamed}"
    )


@pytest.mark.parametrize(
    ("relative", "anchor"),
    sorted(_PROHIBITION_ANCHORS.items()),
)
def test_prohibition_and_qualification_travel_together(
    relative: str, anchor: str
) -> None:
    """A document that forbids the library direction must say which one.

    The bare prohibition -- "never a library" -- is what contradicted the users
    guide. Requiring the qualification in the same document as the prohibition
    means the two cannot drift apart again: moving the rule without its
    explanation fails here.
    """
    text = _read(relative)

    assert anchor in text, (
        f"{relative} no longer carries the prohibition phrase {anchor!r}; if "
        "the rule moved, this test needs to move with it rather than pass "
        "vacuously"
    )
    assert _states_importing_is_supported(text), (
        f"{relative} keeps the prohibition but has lost the qualification, so "
        "it reads as forbidding the Python helpers the users guide documents"
    )


@pytest.mark.parametrize("relative", sorted(_DOCUMENT_HELPER_CLAIMS))
def test_each_downstream_document_keeps_naming_the_helpers(relative: str) -> None:
    """The users guide and the migration guide must keep naming the helpers.

    The users guide is where the helpers are documented and labelled supported;
    the migration guide is where an integration is told which of them are
    changing. A rename that updated one and not the other would leave the
    documentation set describing two different APIs, which is the defect this
    module exists for. Both are checked against the same table so the
    requirement is stated once and each document still fails on its own.
    """
    text = _read(relative)
    required = _DOCUMENT_HELPER_CLAIMS[relative]

    missing = [phrase for phrase in required if phrase not in text]

    assert not missing, (
        f"{relative} no longer carries every phrase it is required to keep, "
        f"because {_DOCUMENT_ROLES[relative]}; missing: {missing}"
    )
