"""Executable contract for the messages a failed VoxelForge call returns.

Roadmap task 1.4.2 translated the MCP error messages from Thai into English.
An error string is not decoration: it is the recovery instruction, and for a
failed call it is the *only* thing the caller reads. A caller who mistypes a
scene name gets that sentence and nothing else, so the sentence has to name
the right remedy.

These tests are separated from ``test_message_contracts.py`` because they pin a
different thing. That module pins what a *successful* call confirms; this one
pins what an *unsuccessful* call instructs, and the two surfaces fail
independently -- a translation pass can leave the confirmations correct while
one rejection still sends the caller to the wrong next step.

Run with ``uv run pytest -q``. Tests that save or load request the
``scene_directory`` fixture so no real ``~/.voxel-forge`` directory is touched.
The ``scene_store`` and ``occupied_store`` fixtures come from ``conftest.py``,
so this module and ``test_message_contracts.py`` drive the same precondition
rather than each constructing their own.
"""

from __future__ import annotations

import typing as typ

import pytest

from voxel_forge import server
from voxel_forge.model_validation import InvalidSceneDataError

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    from pathlib import Path

    # Annotates the ``scene_store`` and ``empty_server_store`` fixture
    # parameters. Both fixtures hand back the store they built, so no test in
    # this module constructs one itself and the import never runs.
    from voxel_forge.model import SceneStore

_SCENE = "house"

# A name that is deliberately absent from the shared ``scene_store`` fixture,
# which registers ``house``. Every lookup-remedy test below asks for this one,
# so the name they share is written once and cannot drift between them.
_ABSENT = "absent"


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


def test_place_many_rejects_a_non_string_payload(scene_store: SceneStore) -> None:
    """A payload that is not text at all must say so, not fail as a parse error.

    The MCP schema declares ``blocks_json`` as a string, but a client can still
    pass a number or an object, and the resulting message is what tells the
    caller their argument was the wrong *type* rather than malformed JSON.
    ``InvalidSceneDataError`` derives from ``ValueError``, so catching that
    still works, and the message is compared in full because "blocks must be a
    JSON string" and "blocks must be a JSON array" differ by one word while
    directing the caller to entirely different fixes.
    """
    with pytest.raises(InvalidSceneDataError) as caught:
        server.voxelforge_place_many(123)  # type: ignore[arg-type]  # MCP schema

    assert caught.value.args[0] == "blocks must be a JSON string", (
        "a non-text payload must name the type defect, not report a parse failure"
    )


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


def test_import_rejection_names_the_format_it_could_not_read(tmp_path: Path) -> None:
    """A file that is not VOX must name the format, not report a codec error.

    The message is translated text, and it is what a caller sees when they
    point the tool at the wrong file. Asserting it in full keeps a regression
    from degrading it into a bare exception repr, which would no longer tell
    the caller which format was expected.
    """
    not_vox = tmp_path / "not-a-vox.vox"
    not_vox.write_bytes(b"this is not a VOX document")

    with pytest.raises(ValueError, match=r"^not a valid \.vox file$") as caught:
        server.voxelforge_import_vox(str(not_vox))

    assert caught.value.args[0] == "not a valid .vox file", (
        "an unreadable import must name the format it expected"
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
    empty_server_store: SceneStore,
    existing_scene: str | None,
    lookup: str,
    expected: str,
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
    if existing_scene is not None:
        empty_server_store.create(existing_scene)

    with pytest.raises(KeyError) as caught:
        server.resolve_scene(lookup)

    assert caught.value.args[0] == expected, (
        f"a lookup of {lookup!r} must raise {expected!r}; a wrong "
        "remedy here sends the caller to the wrong recovery step"
    )


@pytest.mark.parametrize(
    ("tool", "call"),
    [
        ("voxelforge_select_scene", lambda: server.voxelforge_select_scene(_ABSENT)),
        ("voxelforge_preview", lambda: server.voxelforge_preview(_ABSENT)),
        ("voxelforge_get_info", lambda: server.voxelforge_get_info(_ABSENT)),
        ("voxelforge_clear", lambda: server.voxelforge_clear(_ABSENT)),
        ("voxelforge_merge_stats", lambda: server.voxelforge_merge_stats(_ABSENT)),
        (
            "voxelforge_place_block",
            lambda: server.voxelforge_place_block(0, 0, 0, "1", _ABSENT),
        ),
        (
            "voxelforge_set_palette",
            lambda: server.voxelforge_set_palette("9", 1, 2, 3, _ABSENT),
        ),
        (
            "voxelforge_set_voxel_size",
            lambda: server.voxelforge_set_voxel_size(0.5, _ABSENT),
        ),
        ("voxelforge_save", lambda: server.voxelforge_save(_ABSENT)),
        ("voxelforge_export_vox", lambda: server.voxelforge_export_vox(_ABSENT, "")),
        # A shape the rows above do not reach: ``place_many`` is the only bulk
        # edit, so it is the one tool that resolves a scene name alongside a
        # payload argument.
        (
            "voxelforge_place_many",
            lambda: server.voxelforge_place_many("[]", _ABSENT),
        ),
    ],
)
def test_every_scene_name_tool_gives_the_same_lookup_remedy(
    scene_store: SceneStore, tool: str, call: cabc.Callable[[], str]
) -> None:
    """A mistyped scene name must draw one remedy, whichever tool was called.

    A caller who mistypes a name is in exactly one situation, and it does not
    depend on which tool they happened to reach for. If the tools disagree,
    the recovery instruction becomes a function of the tool rather than of
    the mistake, and a caller who learns the remedy from one tool is misled
    by the next -- ``voxelforge_select_scene`` is the tool whose entire
    purpose is naming a scene, so it is the one a caller is most likely to
    hit this error on first.

    The assertion is deliberately on the *message*, not on which helper the
    tool happens to call. Pinning the call site would pass for a tool that
    routed through the adapter and then discarded its wording, which is the
    failure this test exists to catch.
    """
    with pytest.raises(KeyError) as caught:
        call()

    assert caught.value.args[0] == (
        f"scene '{_ABSENT}' is not loaded in this session — call voxelforge_load "
        "for a saved scene, or use the name of an existing session scene"
    ), f"{tool} must send a caller with a mistyped scene name to the same remedy"


def test_layer_index_rejection_names_the_valid_range(
    scene_store: SceneStore,
) -> None:
    """An out-of-range layer index must say what the range actually is.

    "Invalid layer index" leaves the caller to guess whether the count is
    wrong or the index is, and the valid range is not otherwise recoverable
    from a failed call. The scene holds one layer, so the range is ``0..0``:
    the message reports the range for *this* scene rather than a fixed bound,
    which is what makes it actionable.
    """
    with pytest.raises(
        ValueError, match=r"^layer index must be within 0\.\.0$"
    ) as caught:
        server.voxelforge_set_active_layer(5)

    assert caught.value.args[0] == "layer index must be within 0..0", (
        "the rejection must name the range that would have been accepted"
    )


def test_clear_confirmation_names_the_scene_it_emptied(
    occupied_store: SceneStore,
) -> None:
    """Clearing must name the scene, and must not read as a no-op.

    ``clear`` has no other evidence attached to it: the scene remains in the
    registry and merely loses its voxels, so the confirmation is the only
    signal that the call did anything. It echoes the scene name because a
    caller clearing a scene by name needs to know which one was affected.
    """
    assert server.voxelforge_clear() == f"cleared scene '{_SCENE}'", (
        "clear must name the scene it emptied"
    )
    assert server.store.get().block_count() == 0, (
        "the confirmation must describe a scene that is actually empty"
    )
