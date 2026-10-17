"""Executable contract for the operation label on a scene-lookup failure.

``resolve_scene`` writes one INFO record when a lookup fails, and the record
names both the category -- no current scene, or unknown scene -- and the
operation that asked. The category says what went wrong; the operation says
which tool the caller reached for. Without the second field every failing edit
logs the same line as every failing export, so an operator cannot tell a
misbehaving tool from a broken boundary.

The label is a ``SceneOperation`` member passed by the call site, which means
it is exactly the kind of thing a new tool forgets: the code still works, the
recovery message is still right, and only the log is wrong. These tests drive
every advertised tool that resolves a scene through the adapter and require
each one to name its own operation, then assert that the tools driven and the
tools advertised are the same set -- in both directions, so a tool added
without a row here fails rather than escaping the check.

Run with ``uv run pytest -q``. Tools are driven as functions rather than over
the wire: this is about the adapter's record, and the protocol adds nothing to
it.
"""

from __future__ import annotations

import logging
import typing as typ

import pytest
from mcp_wire_helpers import fetch_tools

from voxel_forge import server
from voxel_forge.scene_errors import SceneOperation

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    # Annotates the shared ``scene_store`` fixture parameter, which this module
    # requests by name and never constructs; the import therefore never runs.
    from voxel_forge.model import SceneStore

# The scene every tool below is asked for. It is missing from the shared
# ``scene_store`` fixture, which registers ``house``, so each call takes the
# unknown-scene branch. That branch is the one a mistyped name reaches, and it
# is the branch every scene tool can hit, which makes it the right probe: the
# no-current-scene branch only has one reachable caller shape per tool and is
# already pinned in ``test_failure_messages.py``.
_ABSENT = "absent"

# The scene the shared ``scene_store`` fixture registers, named here because
# the success-direction test below asks for it by name. It matches the ``SCENE``
# in ``conftest.py``; the fixture is what creates it.
_SCENE = "house"

# Every tool that resolves a scene through ``resolve_scene``, with the label
# its call site passes. The mapping is a specification, not a sample: the test
# below fails if the published tool surface grows a scene lookup without a row.
_OPERATIONS: dict[str, tuple[SceneOperation, cabc.Callable[[], str]]] = {
    "voxelforge_select_scene": (
        SceneOperation.SELECT,
        lambda: server.voxelforge_select_scene(_ABSENT),
    ),
    "voxelforge_add_layer": (
        SceneOperation.ADD_LAYER,
        lambda: server.voxelforge_add_layer("top", _ABSENT),
    ),
    "voxelforge_set_active_layer": (
        SceneOperation.SET_ACTIVE_LAYER,
        lambda: server.voxelforge_set_active_layer(0, _ABSENT),
    ),
    "voxelforge_set_palette": (
        SceneOperation.SET_PALETTE,
        lambda: server.voxelforge_set_palette("9", 1, 2, 3, _ABSENT),
    ),
    "voxelforge_set_voxel_size": (
        SceneOperation.SET_VOXEL_SIZE,
        lambda: server.voxelforge_set_voxel_size(0.5, _ABSENT),
    ),
    "voxelforge_preview": (
        SceneOperation.PREVIEW,
        lambda: server.voxelforge_preview(_ABSENT),
    ),
    "voxelforge_get_info": (
        SceneOperation.GET_INFO,
        lambda: server.voxelforge_get_info(_ABSENT),
    ),
    "voxelforge_merge_stats": (
        SceneOperation.MERGE_STATS,
        lambda: server.voxelforge_merge_stats(_ABSENT),
    ),
    "voxelforge_place_block": (
        SceneOperation.PLACE_BLOCK,
        lambda: server.voxelforge_place_block(0, 0, 0, "1", _ABSENT),
    ),
    "voxelforge_place_many": (
        SceneOperation.PLACE_MANY,
        lambda: server.voxelforge_place_many("[]", _ABSENT),
    ),
    "voxelforge_fill_box": (
        SceneOperation.FILL_BOX,
        lambda: server.voxelforge_fill_box(0, 0, 0, 1, 1, 1, "1", _ABSENT),
    ),
    "voxelforge_remove_block": (
        SceneOperation.REMOVE_BLOCK,
        lambda: server.voxelforge_remove_block(0, 0, 0, _ABSENT),
    ),
    "voxelforge_clear": (
        SceneOperation.CLEAR,
        lambda: server.voxelforge_clear(_ABSENT),
    ),
    "voxelforge_save": (
        SceneOperation.SAVE,
        lambda: server.voxelforge_save(_ABSENT),
    ),
    "voxelforge_export_vox": (
        SceneOperation.EXPORT_VOX,
        lambda: server.voxelforge_export_vox(_ABSENT, ""),
    ),
    "voxelforge_export_obj": (
        SceneOperation.EXPORT_OBJ,
        lambda: server.voxelforge_export_obj(_ABSENT, ""),
    ),
    "voxelforge_export_obj_legacy": (
        SceneOperation.EXPORT_OBJ_LEGACY,
        lambda: server.voxelforge_export_obj_legacy(_ABSENT, ""),
    ),
    "voxelforge_export_roblox_merged": (
        SceneOperation.EXPORT_ROBLOX_MERGED,
        lambda: server.voxelforge_export_roblox_merged(_ABSENT, ""),
    ),
}


class _ToolCall(typ.NamedTuple):
    """One tool and the call a test makes to it.

    The two travel together in every row below, and grouping them keeps each
    test within the project's four-parameter limit without dropping a fixture
    it needs.
    """

    tool: str
    call: cabc.Callable[[], str]


@pytest.mark.parametrize(
    ("case", "operation"),
    [
        pytest.param(_ToolCall(name, call), operation, id=name)
        for name, (operation, call) in _OPERATIONS.items()
    ],
)
def test_each_scene_tool_logs_its_own_operation(
    scene_store: SceneStore,
    caplog: pytest.LogCaptureFixture,
    case: _ToolCall,
    operation: SceneOperation,
) -> None:
    """A failed lookup must name the operation, not only the category.

    The record is asserted in full rather than by substring: ``operation=get_info``
    is a substring of ``operation=get_info_extra``, and a tool that passed the
    wrong label would otherwise pass whenever the wrong label happened to share
    a prefix. The category is asserted alongside it because the two fields are
    one record -- a line that names the operation but loses the category would
    be equally unactionable in the other direction.

    ``args[0]`` on the captured ``KeyError`` is not inspected here; the
    recovery wording is `test_failure_messages.py`'s claim. This test is only
    about what reached the log.
    """
    with (
        caplog.at_level(logging.INFO, logger="voxel_forge.server"),
        pytest.raises(KeyError),
    ):
        case.call()

    messages = [record.getMessage() for record in caplog.records]
    expected = f"scene lookup failed operation={operation} category=unknown_scene"
    assert expected in messages, (
        f"{case.tool} must log the operation it was doing; expected "
        f"{expected!r}, got {messages}"
    )


@pytest.mark.parametrize(
    "case",
    [
        pytest.param(_ToolCall(name, call), id=name)
        for name, call in (
            ("voxelforge_preview", lambda: server.voxelforge_preview(_SCENE)),
            ("voxelforge_get_info", lambda: server.voxelforge_get_info(_SCENE)),
            ("voxelforge_merge_stats", lambda: server.voxelforge_merge_stats(_SCENE)),
        )
    ],
)
def test_a_successful_query_neither_logs_nor_publishes(
    scene_store: SceneStore,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
    case: _ToolCall,
) -> None:
    """A read that succeeds must leave no operational trace at the adapter.

    ``resolve_scene`` sits in the path of three read-only tools as well as the
    editing ones, and a lookup that succeeds returns the scene without logging
    anything. That is the property that keeps the failure record meaningful: if
    the adapter logged on success too, a query would be indistinguishable from
    a command in the log, and a maintainer could no longer read the line as
    "this lookup failed".

    The bridge publisher is stubbed to record calls, so this also pins that a
    read does not announce a scene update. Together the two assertions are the
    command/query boundary the finding asked for: a query must not perform the
    command-side effects of logging and publishing.
    """
    published: list[object] = []
    monkeypatch.setattr(server, "_sync_bridge", published.append)

    with caplog.at_level(logging.INFO, logger="voxel_forge.server"):
        case.call()

    messages = [
        record.getMessage()
        for record in caplog.records
        if record.name == "voxel_forge.server"
    ]
    assert not messages, (
        f"{case.tool} is a query; a successful lookup must log nothing, got {messages}"
    )
    assert not published, (
        f"{case.tool} is a query; it must not announce a scene update, but "
        f"published {len(published)} time(s)"
    )


def test_every_advertised_scene_tool_is_driven_here() -> None:
    """The table above must cover the tools that actually resolve a scene.

    A row per tool is not enough: a new tool could be added to the server and
    resolve its scene without ever appearing here, and every test in this
    module would still pass. The reverse direction catches a stale row -- one
    naming a tool the server no longer publishes -- which would otherwise
    keep passing against a function nobody can call.

    The advertised set is the whole tool surface, which is larger than the set
    of scene-resolving tools. Tools that take no scene (``create_scene``,
    ``load``, ``about``, the palette, the builders, the editor launcher) are
    subtracted explicitly, so the comparison is about the scene-lookup surface
    rather than the full inventory. That subtraction is a second, smaller
    specification: adding a scene argument to one of these tools means moving
    it out of this set, and the assertion fails until it does.
    """
    advertised = {tool.name for tool in fetch_tools()}
    scene_independent = {
        "voxelforge_about",
        "voxelforge_build_chibi_bear",
        "voxelforge_build_tree",
        "voxelforge_create_scene",
        "voxelforge_default_palette",
        "voxelforge_import_vox",
        "voxelforge_launch_editor",
        "voxelforge_list_scenes",
        "voxelforge_load",
    }
    expected = advertised - scene_independent

    assert set(_OPERATIONS) == expected, (
        "the operation table must name exactly the tools that resolve a scene; "
        f"missing from the table: {sorted(expected - set(_OPERATIONS))}; "
        f"not published: {sorted(set(_OPERATIONS) - advertised)}"
    )
