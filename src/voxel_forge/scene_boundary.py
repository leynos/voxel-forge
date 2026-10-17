"""Expose the scene registry through the MCP boundary.

Everything in this module is adapter-side: it knows the MCP tool surface, the
recovery wording a client reads, and the operational log a maintainer reads.
The domain model stays free of all three.

The split matters because the two halves fail for different reasons. A lookup
can fail because no scene is current or because the named scene is not
registered; those are domain conditions and live in ``scene_errors``. What a
client should *do* about it, and what the log should say, depends on which tool
asked -- that is adapter policy, so it lives here.

The boundary has a query side and a command side, and the difference is the
point:

``lookup_scene``
    The read path. Reads the registry and lets the typed, transport-neutral
    domain error propagate. No wording, no log, no publication.
``recovery_message``
    The adapter's wording for a failed lookup, kept out of the domain module
    because it names MCP tools.
``recover_lookup_failures``
    The read-tool registration decorator. A read's body calls
    ``lookup_scene`` and renders its result; the decorator is what turns the
    typed failure into :func:`recovery_message` at the client boundary. The
    read handler therefore contains no presentation policy at all, and the
    wording is applied exactly once, in one place.
``resolve_scene``
    The command path, where the failure must also be recorded: it words the
    error *and* logs the operation. Every scene-mutating or scene-exporting
    tool calls this.

The helpers take the store as a parameter rather than reading a module global,
so the translation is testable against a store of its own.

:class:`SceneOperation` is a ``StrEnum`` so a log field, a dictionary key, and
a test comparison all read the same literal, and so an unlisted operation
fails at the call site rather than reaching a log as free text. The values
name the *kind of work* rather than the tool name, so a log line reads
``operation=place_many``: it says what failed without tying the record to the
``voxelforge_`` prefix or to one transport.
"""

from __future__ import annotations

import enum
import functools
import inspect
import logging
import typing as typ

from .scene_errors import NoCurrentSceneError, UnknownSceneError

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    # Annotates parameters and return types only; the runtime needs neither.
    from .model import SceneStore, VoxelScene

_LOG = logging.getLogger(__name__)

_P = typ.ParamSpec("_P")
_R = typ.TypeVar("_R")

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


def recovery_message(scene_name: str) -> str:
    """Word a missing-scene failure as the step the caller should take next.

    Wording only. No log record is written here, so a caller that needs the
    words without the command path can take them.

    This is the MCP adapter's wording, so it lives here rather than with the
    conditions. The message is shared so a mistyped name draws the same remedy
    whichever tool the caller happened to reach for: the mistake is one
    situation, so the instruction must not vary with the tool that surfaced it.

    Parameters
    ----------
    scene_name : str
        The name that was not loaded. It is quoted back so the caller can see
        which name failed, which matters when the name came from a variable
        rather than from the call itself.

    Returns
    -------
    str
        The recovery guidance: load the saved scene, or name one that exists in
        this session.
    """
    return (
        f"scene '{scene_name}' is not loaded in this session — call "
        "voxelforge_load for a saved scene, or use the name of an "
        "existing session scene"
    )


def recover_lookup_failures(
    tool: cabc.Callable[_P, _R],
) -> cabc.Callable[_P, _R]:
    """Word a read tool's lookup failure as the recovery step it implies.

    A read handler calls :func:`lookup_scene` and renders the scene it gets.
    That handler knows nothing about MCP wording, and should not: it is a
    query, so it does not log, does not publish, and does not decide what a
    client should read. This decorator is the MCP boundary for those tools,
    applied where the tool is registered, so the translation happens once,
    above the handler, and the handler stays a query all the way down.

    ``functools.wraps`` preserves the signature the MCP schema is built from,
    so decoration changes the failure wording and nothing about the tool's
    advertised parameters.

    Parameters
    ----------
    tool : Callable
        The registered read tool. It calls :func:`lookup_scene` and may let
        :class:`NoCurrentSceneError` or :class:`UnknownSceneError` escape.

    Returns
    -------
    Callable
        The same tool, with both lookup failures translated to ``KeyError``
        carrying the caller-facing recovery instruction.

    Notes
    -----
    The scene name is recovered by binding the call against the tool's own
    signature, so a caller may pass it by keyword or positionally and the
    decorator needs no per-tool table. Reaching :class:`UnknownSceneError` at
    all means the call already matched the signature, so the bind cannot fail
    here.
    """
    signature = inspect.signature(tool)

    @functools.wraps(tool)
    def wrapped(*args: _P.args, **kwargs: _P.kwargs) -> _R:
        try:
            return tool(*args, **kwargs)
        except NoCurrentSceneError as exc:
            raise KeyError(_NO_CURRENT_SCENE_REMEDY) from exc
        except UnknownSceneError as exc:
            bound = signature.bind(*args, **kwargs)
            scene_name = typ.cast("str", bound.arguments.get("scene_name", ""))
            raise KeyError(recovery_message(scene_name)) from exc

    return wrapped


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

    A read does not share this function. ``preview``, ``get_info`` and
    ``merge_stats`` call :func:`lookup_scene`, so a failed query keeps its
    typed domain error and neither logs nor publishes; their recovery wording
    is applied by :func:`recover_lookup_failures` at registration, which is
    the layer that knows it is answering a client.

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
        raise KeyError(recovery_message(scene_name)) from exc
