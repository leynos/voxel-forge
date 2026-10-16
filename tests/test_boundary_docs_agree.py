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
_IMPORT_IS_SUPPORTED = ("import", "in-process")

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


@pytest.mark.parametrize("relative", _BOUNDARY_DOCUMENTS)
def test_each_boundary_document_states_the_python_helpers_are_supported(
    relative: str,
) -> None:
    """Every document in the set must permit importing the helpers.

    Asserting this per document rather than on the set as a whole is the point:
    the defect was one document forbidding what another documented, and a
    check that concatenated all four would pass while any single one
    contradicted the rest.
    """
    text = _read(relative).lower()

    assert any(term in text for term in _IMPORT_IS_SUPPORTED), (
        f"{relative} describes the consumer boundary without saying that "
        "importing the installed package is supported; a reader of this "
        "document alone can conclude the Python helpers are out of bounds"
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
    lowered = text.lower()
    assert any(term in lowered for term in _IMPORT_IS_SUPPORTED), (
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
