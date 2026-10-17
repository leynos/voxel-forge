"""Expose the scene registry through the MCP boundary.

Everything in this module is adapter-side: it knows the MCP tool surface, the
recovery wording a client reads, and the operational log a maintainer reads.
The domain model stays free of all three.

The split matters because the two halves fail for different reasons. A lookup
can fail because no scene is current or because the named scene is not
registered; those are domain conditions and live in ``scene_errors``. What a
client should *do* about it, and what the log should say, depends on which tool
asked -- that is adapter policy, so it lives here.

Three functions form the boundary, and the ordering is the contract:

``lookup_scene``
    Reads the registry and lets the domain error propagate. No wording, no
    log, no publication.
``query_scene``
    Adds the caller-facing wording for a read. Still no log and no
    publication, so ``preview``, ``get_info`` and ``merge_stats`` cannot gain
    a command's side-effects.
``resolve_scene``
    The command path: words the failure *and* records it. Every scene-mutating
    or scene-exporting tool calls this.

:class:`SceneOperation` is a ``StrEnum`` so a log field, a dictionary key, and
a test comparison all read the same literal, and so an unlisted operation
fails at the call site rather than reaching a log as free text. The values
name the *kind of work* rather than the tool name, so a log line reads
``operation=place_many``: it says what failed without tying the record to the
``voxelforge_`` prefix or to one transport.
"""

from __future__ import annotations

import enum
import logging
import typing as typ

from .scene_errors import NoCurrentSceneError, UnknownSceneError

if typ.TYPE_CHECKING:
    # Annotates parameters and return types only; the runtime needs neither.
    from .model import SceneStore, VoxelScene

_LOG = logging.getLogger(__name__)

# The remedy for a session that has no scene at all. A caller who has not
# created one cannot be told to load or rename it.
_NO_CURRENT_SCENE_REMEDY = "no scene yet — call voxelforge_create_scene first"


class SceneOperation(enum.StrEnum):
    """What a caller was doing when a scene lookup failed.

    A closed set, so a log field never carries caller-supplied text and no two
    operations can collapse into one another by accident. A scene tool adds a
    member here and passes it to :func:`resolve_scene`; adding a tool without
    one is caught by ``tests/test_scene_lookup_logging.py``, which drives every
    advertised scene tool and fails on a record that names no operation.
    """

    SELECT = "select"
    ADD_LAYER = "add_layer"
    SET_ACTIVE_LAYER = "set_active_layer"
    SET_PALETTE = "set_palette"
    SET_VOXEL_SIZE = "set_voxel_size"
    PREVIEW = "preview"
    GET_INFO = "get_info"
    MERGE_STATS = "merge_stats"
    PLACE_BLOCK = "place_block"
    PLACE_MANY = "place_many"
    FILL_BOX = "fill_box"
    REMOVE_BLOCK = "remove_block"
    CLEAR = "clear"
    SAVE = "save"
    EXPORT_VOX = "export_vox"
    EXPORT_OBJ = "export_obj"
    EXPORT_OBJ_LEGACY = "export_obj_legacy"
    EXPORT_ROBLOX_MERGED = "export_roblox_merged"


def _recovery_message(scene_name: str) -> str:
    """Word a missing-scene failure as the step the caller should take next.

    Shared by the command and query paths so a mistyped name draws the same
    remedy whichever tool the caller happened to reach for: the mistake is one
    situation, so the instruction must not vary with the tool that surfaced it.

    Wording only. No log record is written here, which is what lets a query
    reuse it without gaining an operational side-effect.
    """
    return (
        f"scene '{scene_name}' is not loaded in this session — call "
        "voxelforge_load for a saved scene, or use the name of an "
        "existing session scene"
    )


def lookup_scene(scene_store: SceneStore, scene_name: str) -> VoxelScene:
    """Return a registered scene, leaving lookup failures typed and untouched.

    A query, deliberately: it reads the store and either returns the scene or
    lets the domain error propagate. It does not log and does not publish, so a
    caller that only wants the scene pays for neither.

    Parameters
    ----------
    scene_store : SceneStore
        The registry to read, supplied by the caller.
    scene_name : str
        Name of the target scene; empty means the current scene.

    Returns
    -------
    VoxelScene
        The requested scene.

    Raises
    ------
    NoCurrentSceneError
        If nothing is current and no name was given.
    UnknownSceneError
        If the named scene is not registered.
    """
    return scene_store.get(scene_name or None)


def query_scene(scene_store: SceneStore, scene_name: str) -> VoxelScene:
    """Return a scene for a read, translating the failure but recording nothing.

    The read-side counterpart of :func:`resolve_scene`: the caller gets the
    same recovery wording, so a mistyped name is answered the same way by
    ``get_info`` as by ``place_block``, but nothing is logged and nothing is
    published. A query that fails is a caller mistake, not an operational
    event, and a read has no mutation to announce.

    Parameters
    ----------
    scene_store : SceneStore
        The registry to read, supplied by the caller.
    scene_name : str
        Name of the target scene; empty means the current scene.

    Returns
    -------
    VoxelScene
        The requested scene.

    Raises
    ------
    KeyError
        If no scene is current, or the named scene is not registered. The
        message names the tool to call next.
    """
    try:
        return lookup_scene(scene_store, scene_name)
    except NoCurrentSceneError as exc:
        raise KeyError(_NO_CURRENT_SCENE_REMEDY) from exc
    except UnknownSceneError as exc:
        raise KeyError(_recovery_message(scene_name)) from exc


def resolve_scene(
    scene_store: SceneStore,
    scene_name: str = "",
    *,
    operation: SceneOperation,
) -> VoxelScene:
    """Return a registered scene, wording and recording a lookup failure.

    The command-side adapter. It turns the domain's transport-neutral errors
    into the instruction an MCP client reads and acts on, and writes the
    operational record that says which tool asked. The two failures need
    different remedies and are distinct domain types, so the branch is on type
    rather than on matching message text: a session with no scene at all is
    told to create one, while a caller who named a scene has already created
    one and is directed to load a saved scene or correct the name.

    Keeping the lookup, the wording and the record separable is what lets a
    read-only tool share the wording without the side-effect: ``preview``,
    ``get_info`` and ``merge_stats`` call :func:`query_scene`, so a failed
    query logs nothing and publishes nothing.

    ``scene_store`` is supplied by the caller rather than read from a module
    global. The store is the dependency this translation drives, so passing it
    makes the translation testable against a store of its own and keeps the
    function independent of whichever instance the process happens to hold.
    Tool modules pass ``server.store``, so the process still has exactly one.

    ``operation`` is keyword-only and required: a lookup that cannot say what
    asked for the scene would log a failure nobody can act on. It comes from
    the closed set in :class:`SceneOperation`, so the value reaches the log as
    a known label rather than as free text. The scene name is deliberately not
    logged; it is caller data, and the category plus the operation is what a
    maintainer needs to see whether one tool or all of them are failing.

    Parameters
    ----------
    scene_store : SceneStore
        The registry to read, supplied by the caller.
    scene_name : str, optional
        Name of the target scene; empty means the current scene.
    operation : SceneOperation
        What the caller was doing, for the failure record.

    Returns
    -------
    VoxelScene
        The requested scene.

    Raises
    ------
    KeyError
        If no scene is current, or the named scene is not registered. The
        message names the tool to call next.
    """
    try:
        return lookup_scene(scene_store, scene_name)
    except NoCurrentSceneError as exc:
        _LOG.info(
            "scene lookup failed operation=%s category=no_current_scene", operation
        )
        raise KeyError(_NO_CURRENT_SCENE_REMEDY) from exc
    except UnknownSceneError as exc:
        _LOG.info("scene lookup failed operation=%s category=unknown_scene", operation)
        raise KeyError(_recovery_message(scene_name)) from exc
