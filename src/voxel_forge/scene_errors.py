"""Scene-lookup failures, and the closed set of operations that can raise them.

These are domain conditions rather than adapter failures: a caller named a
scene that was not there, or named nothing while nothing was current. They
live apart from :mod:`voxel_forge.model_validation` because that module is
about *field* validity -- palette values, name length, voxel size bounds -- and
a registry or a tool that raises a lookup failure should not have to import
those to spell it. Splitting them keeps each module's imports saying what it
actually depends on.

Nothing here names an MCP tool, or any message a client should read. The
domain states the condition; ``resolve_scene`` in :mod:`voxel_forge.server`
turns it into a recovery instruction, because that wording is the adapter's
responsibility. That split is what keeps the model free of the tool surface.

:class:`SceneOperation` is the closed set of operations a lookup can serve. It
is a ``StrEnum`` so a log field, a dictionary key, and a test comparison all
read the same literal, and so an unlisted operation fails at the call site
rather than reaching a log as free text. The values name the *kind of work*,
which is what a maintainer needs to tell one failing tool from a failure of
the whole boundary.
"""

from __future__ import annotations

import enum


class NoCurrentSceneError(KeyError):
    """No scene is current in this session.

    A domain condition, distinct from :class:`UnknownSceneError`: the caller
    named nothing and nothing was current. Both are ``KeyError`` so existing
    callers keep working, but they are separate types so the adapter can give
    each its own recovery instruction instead of inferring intent from a
    message string.

    The message is deliberately transport-neutral. Naming an MCP tool here
    would make the domain model depend on the tool surface, which is the
    adapter's concern; ``resolve_scene`` in ``server`` attaches the
    caller-facing wording.
    """

    def __init__(self) -> None:
        super().__init__("no scene is current in this session")


class UnknownSceneError(KeyError):
    """A named scene is not registered in this session.

    Separate from :class:`NoCurrentSceneError` because a caller who named a
    scene has already created one and needs a different remedy: load a saved
    scene, or correct the name. ``select`` raises this too, since a selection
    target is named.

    The name is carried in the message so the failure is diagnosable from a
    log, where no adapter has translated it yet.
    """

    def __init__(self, name: str) -> None:
        super().__init__(f"scene {name!r} is not registered in this session")
        self.name = name


class SceneOperation(enum.StrEnum):
    """What a caller was doing when a scene lookup failed.

    A closed set, so a log field never carries caller-supplied text and no two
    operations can collapse into one another by accident. A scene tool adds a
    member here and passes it to ``resolve_scene``; adding a tool without one
    is caught by ``tests/test_scene_lookup_logging.py``, which drives every
    advertised scene tool and fails on a record that names no operation.

    The members are the tool surface's verbs rather than its tool names. A log
    line reads ``operation=place_many``, which says what failed without
    tying the record to the ``voxelforge_`` prefix or to one transport.
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
