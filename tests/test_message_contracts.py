"""Executable contract for the MCP messages this release translates.

Roadmap task 1.4.2 translated the MCP instructions, tool descriptions,
confirmations, and error messages from Thai into English, because an MCP
client's language model reads those strings and they are the tool's discovery
surface. The translation changed text a caller sees and acts on, so the text
is part of the contract and is pinned here.

The distinction that matters is between a message and a *shape*. Asserting that
a response merely contains "placed" passes for "not placed", so a caller-facing
confirmation is asserted in full where it is stable, and the tests that only
need the contract assert on the value they depend on rather than on a
substring. The error strings are pinned because their wording is the recovery
instruction: a caller who mistypes a scene name reads that message and nothing
else.

Run with ``uv run pytest -q``. Tests that save, load, or export request the
``scene_directory`` fixture so no real ``~/.voxel-forge`` directory is touched.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from voxel_forge import server
from voxel_forge.model import SceneStore

# The scene every confirmation test operates on. Shared rather than repeated so
# the name a response echoes is one value the expectations can be read against,
# and so the setup itself does not become the thing the tests have in common.
_SCENE = "house"

# Coordinates that carry meaning, named so a reader can tell them apart. The
# origin is where a placed voxel is expected to be found; the neighbour sits
# against it, which is what makes two voxels merge into a single OBJ part; the
# miss is deliberately off in empty space, so a removal there finds nothing.
_ORIGIN = (0, 0, 0)
_NEIGHBOUR = (1, 0, 0)
_MISS = (9, 9, 9)


@pytest.fixture
def scene_store(empty_server_store: SceneStore) -> SceneStore:
    """Provide the server's store with one scene already created.

    Most confirmations only make sense once a scene exists, so the precondition
    lives here rather than as a ``create`` call repeated in every test. It
    builds on ``empty_server_store`` so the real store and bridge are still
    replaced for the duration of the test.
    """
    empty_server_store.create(_SCENE)
    return empty_server_store


@pytest.fixture
def occupied_store(scene_store: SceneStore) -> SceneStore:
    """Provide the scene store holding one voxel at the origin.

    Tests that act on existing geometry rather than creating it share this
    precondition, so the voxel is placed here instead of by a call repeated at
    the top of each. Colour ``2`` is the palette entry the confirmations under
    test echo back.
    """
    server.voxelforge_place_block(*_ORIGIN, "2")
    return scene_store


def test_edit_confirmations_name_the_operation_and_its_result(
    scene_store: SceneStore,
) -> None:
    """A confirmation must state what happened, in English, with the count.

    The em dash and the structured summary are deliberate: a client reads the
    whole line, so the operation, its parameters, and the resulting total are
    one sentence rather than a bare status word. Asserting the whole string
    keeps a substring like "not placed" from satisfying the check.
    """
    assert server.voxelforge_place_block(*_ORIGIN, "2") == (
        "placed (0,0,0) colour '2' — 1 blocks total"
    ), "place_block must report its coordinate, colour, and running total"
    assert server.voxelforge_fill_box(1, 2, 0, 0, 0, 0, "3") == (
        "filled 2 voxels with colour '3' — 3 blocks total"
    ), "fill_box must report how many voxels it filled and the new total"


@pytest.mark.parametrize(
    ("coordinate", "expected"),
    [
        (_ORIGIN, "removed"),
        (_MISS, "no voxel there"),
    ],
)
def test_removal_confirmation_distinguishes_hit_from_miss(
    occupied_store: SceneStore, coordinate: tuple[int, int, int], expected: str
) -> None:
    """Removing from an empty coordinate is not the same outcome as removing.

    Both calls succeed, so the response is the only signal separating them.
    Collapsing the two into one word would leave a caller unable to tell an
    edit that changed the scene from one that did nothing. The two outcomes are
    one truth table, so they are rows here rather than two parallel assertions
    that must be kept in step by hand.
    """
    assert server.voxelforge_remove_block(*coordinate) == expected, (
        f"removing at {coordinate} must report {expected!r}, because the two "
        "removal outcomes are identical to a caller who only sees success"
    )


def test_scene_and_layer_confirmations_name_the_scene(
    empty_server_store: SceneStore,
) -> None:
    """Scene operations must name the scene they acted on and their effect."""
    assert server.voxelforge_create_scene(_SCENE) == (
        f"Created scene '{_SCENE}' (initial layer: Layer 1)"
    ), "create_scene must name the scene and its initial layer"

    assert server.voxelforge_add_layer("top") == (
        f"Added layer 'top' to '{_SCENE}' — 2 layers in total"
    ), "add_layer must name the layer, the scene, and the new total"

    assert server.voxelforge_select_scene(_SCENE) == (
        f"Selected scene '{_SCENE}' (0 blocks)"
    ), "select_scene must name the scene and its size"


def test_build_confirmations_report_the_resolution_they_used(
    scene_store: SceneStore,
) -> None:
    """A procedural build must report its counts and the resolution it applied.

    The resolution is not otherwise recoverable from the result: a caller who
    asks for ``resolution=8`` and reads only a voxel count cannot tell a dense
    build from a sparse one, because both report a total.

    The counts are pinned because the generators are deterministic --
    ``procedural`` carries no randomness -- so the numbers assert what the build
    actually produces rather than whatever it happened to emit. A regression
    that halves the geometry shows up here instead of nowhere. The tree
    confirmation also carries the next step, since a build produces a scene the
    caller has not seen yet.
    """
    assert server.voxelforge_build_tree(name="oak", resolution=2) == (
        "Built tree 'oak' — 2422 voxels, voxel_size=0.5 (resolution 2x)\n"
        "Open the editor to view it in 3D, or run voxelforge_preview for an "
        "ASCII check"
    ), "the tree confirmation must name its resolution and the next step"

    assert server.voxelforge_build_chibi_bear(name="bear", resolution=2) == (
        "Built chibi bear 'bear' — 2411 voxels (resolution 2)"
    ), "the bear confirmation must name its resolution"


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ('{"not": "an array"}', "blocks must be a JSON array"),
        ('"a string"', "blocks must be a JSON array"),
        ('[["short"]]', "invalid block row: ['short']"),
    ],
)
def test_place_many_rejection_messages_name_the_defect(
    scene_store: SceneStore, payload: str, message: str
) -> None:
    """A rejected bulk payload must say which rule it broke.

    These strings are the recovery instruction: the caller sees the message and
    no other explanation of why the call failed, so each rejection names the
    rule rather than reporting a generic parse failure. The row-level case
    echoes the offending row, because "invalid block row" alone does not tell a
    caller which of their rows was malformed.
    """
    with pytest.raises(ValueError, match="^" + message.replace("[", r"\[") + "$"):
        server.voxelforge_place_many(payload)


def test_place_many_confirmation_counts_voxels_and_totals(
    scene_store: SceneStore,
) -> None:
    """A bulk placement must report the rows applied and the resulting total."""
    assert server.voxelforge_place_many('[[1,1,1,"4"]]') == (
        f"placed 1 voxels in '{_SCENE}' — 1 blocks total"
    ), "place_many must name the scene and the counts it applied"


def test_export_confirmations_name_the_path_they_wrote(
    occupied_store: SceneStore, tmp_path: Path
) -> None:
    """An export must report the path it wrote and what it put in the file.

    The destination is the part a caller cannot infer, because the merge
    setting changes which file is written and the report is where the caller
    learns which one to open. A second voxel is placed adjacent to the first so
    the two merge into a single box, which is what makes the ``parts`` count
    distinguish a merged export from an unmerged one rather than being a
    constant the test repeats on both branches.

    Destinations are passed explicitly rather than left to default, so the test
    cannot write into a developer's real ``~/.voxel-forge/exports`` directory.
    """
    server.voxelforge_place_block(*_NEIGHBOUR, "2")

    merged = tmp_path / "merged.obj"
    assert server.voxelforge_export_obj(_SCENE, str(merged)) == (
        f"export .obj -> {merged} (1 parts from 2 voxels, merge=True)"
    ), "a merged export must report the merged part count"

    unmerged = tmp_path / "unmerged.obj"
    assert server.voxelforge_export_obj(_SCENE, str(unmerged), merge_boxes=False) == (
        f"export .obj -> {unmerged} (2 parts from 2 voxels, merge=False)"
    ), "an unmerged export must report one part per voxel"

    vox = tmp_path / "scene.vox"
    assert server.voxelforge_export_vox(_SCENE, str(vox)) == (
        f"export .vox → {vox} (2 voxels)"
    ), "the VOX export must name its destination and count"


def test_absent_scene_load_names_the_scene_and_the_path(
    scene_directory: Path,
) -> None:
    """A load of a scene that was never saved must name what could not be found.

    The path is included because the message is the only place a caller learns
    where the tool looked; without it, a scene saved under a different store
    looks identical to a typo in the name.
    """
    with pytest.raises(FileNotFoundError, match="no scene 'missing' at ") as caught:
        server.voxelforge_load("missing")

    assert str(scene_directory) in str(caught.value), (
        "the message must name the directory that was searched"
    )


@pytest.mark.parametrize(
    ("existing_scene", "lookup", "expected"),
    [
        (
            None,
            "",
            "no scene yet — call voxelforge_create_scene first",
        ),
        (
            "present",
            "absent",
            (
                "scene 'absent' is not loaded in this session — call "
                "voxelforge_load for a saved scene, or use the name of an "
                "existing session scene"
            ),
        ),
    ],
)
def test_scene_lookup_failures_give_the_matching_remedy(
    existing_scene: str | None, lookup: str, expected: str
) -> None:
    """The two lookup failures must not share one recovery instruction.

    Both raise ``KeyError``, so the message is what tells a caller whether they
    need to create a scene or correct a name. A caller who already created one
    and mistyped it is sent to ``voxelforge_load`` or to an existing name; only
    a session with no scene at all is told to create one.

    Each message is compared in full rather than by substring. A substring
    check for ``"voxelforge_load"`` passes for a message that also offers the
    wrong remedy, and passes for one that names the scene but then tells the
    caller to create a scene anyway -- the precise confusion this test exists
    to prevent. ``args[0]`` is read instead of ``str()`` because ``KeyError``
    repr-quotes its argument, so ``str()`` would be compared against the
    message wrapped in quote characters.

    This drives the adapter's ``resolve_scene``, not ``SceneStore.get``. The
    recovery wording names MCP tools, which is the adapter's concern; asserting
    it against the domain object would require the domain to know which tools
    exist. The domain side of the same distinction is pinned in
    ``test_model_readiness.py``, on the exception types.

    An empty name means the caller passed no name at all, which is the case
    that reaches the no-current-scene branch.
    """
    store = SceneStore()
    if existing_scene is not None:
        store.create(existing_scene)
    server.store = store

    with pytest.raises(KeyError) as caught:
        server.resolve_scene(lookup)

    assert caught.value.args[0] == expected, (
        f"a lookup of {lookup!r} must raise {expected!r}; a wrong "
        "remedy here sends the caller to the wrong recovery step"
    )


def test_save_and_load_confirmations_survive_a_round_trip(
    occupied_store: SceneStore, scene_directory: Path
) -> None:
    """Saving and reloading must report the path written and the count restored.

    Both confirmations were translated from Thai in this release, and both were
    guarded only by a substring check elsewhere in the suite -- ``"Saved" in
    ...`` and ``"Loaded" in ...``. Those pass for a message that names the wrong
    scene, reports the wrong count, or omits the path entirely, so neither
    pins the sentence a client actually reads.

    The count is asserted after reloading into a fresh store, which is what
    makes it evidence rather than an echo: the confirmation is compared against
    what the reloaded scene really holds, so a hardcoded or stale count in the
    message fails. ``scene_directory`` keeps the write in a temporary
    directory; without it the save would land in a developer's real
    ``~/.voxel-forge/scenes``.
    """
    server.voxelforge_place_block(*_ORIGIN, "2")

    saved = server.voxelforge_save(_SCENE)
    assert saved == f"Saved '{_SCENE}' to {scene_directory / f'{_SCENE}.json'}", (
        "save must name the scene and the exact path it wrote"
    )

    server.store = SceneStore()
    loaded = server.voxelforge_load(_SCENE)
    assert loaded == f"Loaded '{_SCENE}' (1 blocks)", (
        "load must name the scene and the count it restored"
    )


def _guide_response_lines() -> list[str]:
    """Return the response examples the users guide prints in its code block.

    The guide carries more than one ``text`` block -- the bridge diagnostics are
    the first -- so the block is located by its content rather than by position.
    Selecting the first block would compare the responses against log lines and
    fail for the wrong reason.
    """
    guide = (Path(__file__).resolve().parents[1] / "docs" / "users-guide.md").read_text(
        encoding="utf-8"
    )
    for block in guide.split("```text")[1:]:
        body = block.split("```", 1)[0]
        responses = [
            line.split("->", 1)[1].strip() for line in body.splitlines() if "->" in line
        ]
        if responses:
            return responses
    msg = "docs/users-guide.md carries no `text` block of `tool -> response` lines"
    raise AssertionError(msg)


def test_users_guide_quotes_responses_the_tools_actually_return(
    scene_store: SceneStore, scene_directory: Path
) -> None:
    """The users guide's example responses must be the real ones.

    The guide paraphrases nothing here: it prints the strings a client sees, so
    a change to a confirmation that does not reach the guide leaves a
    documented response that no longer exists. That is the same defect class as
    the rest of this branch -- a document asserting something the code does not
    do -- except that the document is the operator's only description of the
    surface, so drift is invisible until a caller compares the two.

    Each quoted line is reproduced by calling the tool that emits it, so the
    example is checked as one coherent run rather than as a set of
    independently plausible lines.
    """
    emitted = [
        server.voxelforge_place_block(*_ORIGIN, "2"),
        server.voxelforge_fill_box(1, 2, 0, 0, 0, 0, "3"),
        server.voxelforge_place_many('[[1,1,1,"4"]]'),
        server.voxelforge_add_layer("top"),
        server.voxelforge_select_scene(_SCENE),
    ]

    quoted = _guide_response_lines()

    missing = [response for response in emitted if response not in quoted]
    assert not missing, (
        "these responses are emitted but not quoted in docs/users-guide.md:\n  "
        + "\n  ".join(missing)
    )
