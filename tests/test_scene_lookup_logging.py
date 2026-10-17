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
each command to name its own operation, then assert that the tools driven and
the tools advertised are the same set -- in both directions, so a tool added
without a row here fails rather than escaping the check.

The reads are the exception, and are driven separately. Their handler calls
``lookup_scene`` and returns; the typed domain error crosses the handler
unchanged, and the registration decorator ``recover_lookup_failures`` is what
words it for the client. A read is therefore asserted to leave no record and
no publication on both its failure and its success paths, and -- at the
boundary -- to word both lookup failures as distinct recovery instructions.

Run with ``uv run pytest -q``. Tools are driven as functions rather than over
the wire: this is about the adapter's record, and the protocol adds nothing to
it.
"""

from __future__ import annotations

import contextlib
import functools
import logging
import typing as typ

import pytest
from mcp_wire_helpers import fetch_tools

from voxel_forge import server
from voxel_forge.scene_boundary import SceneOperation

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

# The logger the adapter records under. It is ``scene_boundary``'s module
# logger, not ``voxel_forge.server``: the record is written where the domain
# type is still known, and scoping ``caplog`` to the same name is what makes a
# record from another module fail the assertion instead of padding it.
_LOGGER = "voxel_forge.scene_boundary"

# Every *command* that resolves a scene through ``resolve_scene``, with the
# label its call site passes. The mapping is a specification, not a sample: the
# test below fails if the published tool surface grows a scene-lookup command
# without a row.
_OPERATIONS: dict[str, tuple[SceneOperation, cabc.Callable[[], object]]] = {
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

# The read-only tools, which reach the scene through ``lookup_scene`` and so
# must never log or publish. They are listed apart from ``_OPERATIONS`` because
# the two groups have opposite contracts; the coverage test below requires the
# union to be exactly the scene-resolving surface.
_QUERY_TOOLS: dict[str, cabc.Callable[..., str]] = {
    "voxelforge_preview": server.voxelforge_preview,
    "voxelforge_get_info": server.voxelforge_get_info,
    "voxelforge_merge_stats": server.voxelforge_merge_stats,
}


class _ToolCall(typ.NamedTuple):
    """One tool and the call a test makes to it.

    The two travel together in every row below, and grouping them keeps each
    test within the project's four-parameter limit without dropping a fixture
    it needs.
    """

    tool: str
    call: cabc.Callable[[], object]


class _QueryCase(typ.NamedTuple):
    """One read-only tool, its call, and whether that call must fail.

    ``raises`` and ``empty`` are data rather than fixture parameters so one
    parametrized test can drive every branch and still assert the same
    no-log, no-publication contract. ``empty`` selects the fixture state: a
    session with no scene at all, versus the shared one that has ``house``.
    """

    tool: str
    call: cabc.Callable[[], object]
    raises: bool
    empty: bool = False


@pytest.mark.parametrize(
    ("case", "operation"),
    [
        pytest.param(_ToolCall(name, call), operation, id=name)
        for name, (operation, call) in _OPERATIONS.items()
    ],
)
def test_each_scene_command_logs_its_own_operation(
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
        caplog.at_level(logging.INFO, logger=_LOGGER),
        pytest.raises(KeyError),
    ):
        case.call()

    messages = [record.getMessage() for record in caplog.records]
    expected = f"scene lookup failed operation={operation} category=unknown_scene"
    assert expected in messages, (
        f"{case.tool} must log the operation it was doing; expected "
        f"{expected!r}, got {messages}"
    )


def _drive_query(
    case: _QueryCase,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Drive one read-only tool and assert it left no operational trace.

    Both directions of the query contract end in the same two assertions, so
    they live here: a guard that silenced only the failing branch would pass
    one test and fail the other, and the difference between the two tests is
    only which branch they drive.

    The publisher is stubbed to record its calls, which is what makes "a read
    does not announce a scene update" observable rather than merely unasserted.
    """
    published: list[object] = []
    monkeypatch.setattr(server, "_sync_bridge", published.append)
    failure = pytest.raises(KeyError) if case.raises else contextlib.nullcontext()

    with caplog.at_level(logging.INFO, logger=_LOGGER), failure:
        case.call()

    messages = [
        record.getMessage() for record in caplog.records if record.name == _LOGGER
    ]
    outcome = "failed" if case.raises else "successful"
    assert not messages, (
        f"{case.tool} is a query; a {outcome} lookup must log nothing, got {messages}"
    )
    assert not published, (
        f"{case.tool} is a query; it must not announce a scene update, but "
        f"published {len(published)} time(s)"
    )


def _query_cases() -> list[pytest.ParameterSet]:
    """Build one row per read tool, branch, and scene argument.

    Three branches are driven, and each has its own reason: the unknown name
    is the mistyped-name path a caller reaches most often; the empty name is
    the no-current-scene path, which words a different remedy; and the success
    path is what a guard that silenced only failures would leave broken. The
    scene argument is data rather than a separate call builder so the three
    cannot drift apart.
    """
    return [
        pytest.param(
            _QueryCase(
                tool,
                functools.partial(function, scene_name),
                raises,
                empty=not scene_name,
            ),
            id=f"{tool}-{branch}",
        )
        for branch, scene_name, raises in (
            ("unknown-scene", _ABSENT, True),
            ("no-current-scene", "", True),
            ("succeeds", _SCENE, False),
        )
        for tool, function in _QUERY_TOOLS.items()
    ]


@pytest.mark.parametrize("case", _query_cases())
def test_a_query_neither_logs_nor_publishes(
    empty_server_store: SceneStore,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
    case: _QueryCase,
) -> None:
    # The no-scene row needs an empty registry, and the other two need the
    # shared scene. ``empty_server_store`` is requested directly and only
    # populated when the row asks for it, so no row has to reach across
    # fixtures for its precondition.
    """A read must stay a query on every branch it can take.

    ``preview``, ``get_info`` and ``merge_stats`` all need the scene, and all
    three are reads. Routing them through the command-side ``resolve_scene``
    would make a lookup failure emit an operational record and, worse, put a
    publication policy in a query path. The handler calls ``lookup_scene``
    instead, and the boundary decorator words the failure above it, so neither
    the log nor the bridge hears from a read.

    Every branch is driven deliberately. A guard that silenced only the failure
    branch would pass two-thirds of this table and miss the read that wrongly
    announces itself on success, which is the branch a caller reaches in normal
    use. The two failures are separate rows because they word different
    remedies, and a decorator that collapsed them would leave one row passing.
    """
    if not case.empty:
        empty_server_store.create(_SCENE)
    _drive_query(case, caplog, monkeypatch)


def test_every_advertised_scene_tool_is_driven_here() -> None:
    """The tables above must cover the tools that actually resolve a scene.

    A row per tool is not enough: a new tool could be added to the server and
    resolve its scene without ever appearing here, and every test in this
    module would still pass. The reverse direction catches a stale row -- one
    naming a tool the server no longer publishes -- which would otherwise
    keep passing against a function nobody can call.

    Commands and queries are covered together, in both directions: a read moved
    onto the command path (or the reverse) would otherwise drop out of the
    checked set silently, and the two groups have opposite contracts.

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
    covered = set(_OPERATIONS) | set(_QUERY_TOOLS)

    assert covered == expected, (
        "the operation tables must name exactly the tools that resolve a scene; "
        f"missing from the tables: {sorted(expected - covered)}; "
        f"not published: {sorted(covered - advertised)}"
    )
