"""MCP Server — VoxelForge (Goxel-inspired) for Cursor, Claude, and other AI clients."""

from __future__ import annotations

import contextlib
import json
import logging
import typing as typ

if typ.TYPE_CHECKING:
    import collections.abc as cabc
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from . import bridge as bridge_module
from .bridge import BRIDGE_HTTP_PORT as BRIDGE_HTTP_PORT
from .bridge import current_ports, notify_scene_update, start_bridge_background
from .export_roblox import to_luau_merged as to_luau_merged
from .export_roblox import write_luau_file as write_luau_file
from .lifecycle_log import emit_lifecycle
from .mesh_merge import merge_stats as merge_stats
from .model import DEFAULT_PALETTE as DEFAULT_PALETTE
from .model import SceneStore, VoxelScene
from .model_validation import BLOCK_ROW_LENGTH, InvalidSceneDataError
from .paths import exports_dir as _exports_dir
from .preview import summary as summary
from .procedural import build_chibi_bear as build_chibi_bear
from .procedural import build_tree as build_tree
from .scene_errors import NoCurrentSceneError as NoCurrentSceneError
from .scene_errors import SceneOperation
from .scene_errors import UnknownSceneError as UnknownSceneError
from .scene_store import list_saved_scenes as list_saved_scenes
from .scene_store import load_scene as load_scene
from .scene_store import save_scene as save_scene
from .vox_io import export_obj as export_obj
from .vox_io import export_vox as export_vox
from .vox_io import import_vox as import_vox

mcp = FastMCP(
    "VoxelForge",
    instructions=(
        "VoxelForge — a Goxel-style 3D voxel builder "
        "(24-bit RGB, layers, export .vox/.obj).\n"
        "Typical flow: voxelforge_create_scene → voxelforge_place_many / "
        "voxelforge_fill_box → voxelforge_preview → voxelforge_export_vox "
        "or voxelforge_export_obj\n"
        "Open the 3D editor: voxelforge_launch_editor\n"
        "Supports importing MagicaVoxel (.vox) files that Goxel can open."
    ),
)

store = SceneStore()
# Scene-lookup failures reach a caller as a recovery message, which is the
# right thing for the caller and invisible to whoever operates the server: a
# client retrying a mistyped name looks, from outside, exactly like an idle
# server. These failures are logged at the boundary where the domain type is
# still known, so the two categories are distinguishable in a log without
# parsing the translated message -- and before ``resolve_scene`` replaces the
# message with wording that names an MCP tool. The scene name is not logged:
# it is caller data, and the category plus the operation is what a maintainer
# needs to see whether one tool or all of them are failing.
_LOG = logging.getLogger(__name__)
MAX_TOOL_VOXELS: int = 100_000
# Bounds the raw request before json.loads materialises it. At the limit above a
# well-formed payload is about 2.5 million characters, so this leaves room for
# formatting while still refusing a payload that could exhaust memory.
MAX_BLOCKS_JSON_CHARS: int = 8_000_000


def _announce_startup(bridge_mode: str, bridge_state: str) -> None:
    """Report the startup mode on stderr, keeping stdout protocol-only.

    A headless run and a run whose bridge failed to start otherwise look
    identical to an operator: the process blocks on stdio either way, and the
    endpoint line is printed only once the listener is up. These fields name
    the mode that was *requested* and the state that was *reached*, so the two
    cases are distinguishable. ``main`` only reaches the "eager" mode once
    ``_ensure_bridge`` has returned, so an eager start that fails raises before
    this runs rather than reporting a state it never held.
    """
    emit_lifecycle(
        "server", "server_start", bridge_mode=bridge_mode, bridge_state=bridge_state
    )


def _ensure_bridge(trigger: str) -> None:
    """Start the bridge if needed and hand it this module's scene registry.

    ``trigger`` names the request that caused the start, so a log reader can
    tell a startup-requested bridge from one an MCP client opened by calling
    ``voxelforge_launch_editor``. Callers pass one of two fixed labels rather
    than anything from the request itself, so the field stays a small closed
    set that a log query can group by.

    The line marks a transition, so it is emitted only when this call found the
    bridge down. A later ``voxelforge_launch_editor`` against an already-running
    bridge is a no-op and must not report a second start. The pre-check is a
    plain read of the published ports; it is exact here because every caller
    serializes its own start (``main`` is single-threaded, and the MCP tool
    holds ``_editor_lock``).
    """
    was_running = current_ports() is not None
    start_bridge_background()
    bridge_module.use_store(store)
    if not was_running:
        emit_lifecycle("server", "bridge_start", trigger=trigger)


def _sync_bridge(scene: VoxelScene) -> None:
    """Notify bridge subscribers when a bridge is running.

    Scene mutations must not start the bridge: a headless or sandboxed run
    should never bind a port. The bridge starts only when an editor is
    requested (`voxelforge_launch_editor`) or when the server is run with
    `--bridge`.

    Parameters
    ----------
    scene : VoxelScene
        The scene whose contents changed.
    """
    if current_ports() is None:
        return
    notify_scene_update(scene)


def _parse_blocks_json(blocks_json: str) -> list[tuple[int, int, int, str]]:
    """
    Parse a bulk voxel JSON array, rejecting oversized text before decoding.

    Raises ``ValueError`` — including ``json.JSONDecodeError`` — when the text
    exceeds ``MAX_BLOCKS_JSON_CHARS``, is not a JSON array, holds more than
    ``MAX_TOOL_VOXELS`` rows, or carries a row shorter than four entries.
    """
    if not isinstance(blocks_json, str):
        msg = "blocks must be a JSON string"
        raise InvalidSceneDataError(msg)
    if len(blocks_json) > MAX_BLOCKS_JSON_CHARS:
        msg = f"blocks payload must be at most {MAX_BLOCKS_JSON_CHARS:,} characters"
        raise InvalidSceneDataError(msg)
    data = json.loads(blocks_json)
    if not isinstance(data, list):
        msg = "blocks must be a JSON array"
        raise InvalidSceneDataError(msg)
    if len(data) > MAX_TOOL_VOXELS:
        msg = f"place_many supports at most {MAX_TOOL_VOXELS:,} voxels per call"
        raise InvalidSceneDataError(msg)
    out: list[tuple[int, int, int, str]] = []
    for row in data:
        if not isinstance(row, (list, tuple)) or len(row) < BLOCK_ROW_LENGTH:
            msg = f"invalid block row: {row}"
            raise InvalidSceneDataError(msg)
        out.append((int(row[0]), int(row[1]), int(row[2]), str(row[3])))
    return out


def resolve_scene(
    scene_store: SceneStore,
    scene_name: str = "",
    *,
    operation: SceneOperation,
) -> VoxelScene:
    """Return a registered scene, wording a lookup failure as a recovery step.

    This is where the domain's transport-neutral errors become the caller-facing
    instruction an MCP client reads and acts on, which is why it lives in the
    adapter rather than in ``SceneStore``. The two failures need different
    remedies and are distinct domain types, so the branch is on type rather than
    on matching message text: a session with no scene at all is told to create
    one, while a caller who named a scene has already created one and is directed
    to load a saved scene or correct the name.

    ``scene_store`` is supplied by the caller rather than read from a module
    global. The store is the dependency this translation drives, so passing it
    makes the translation testable against a store of its own and keeps the
    function independent of whichever instance the process happens to hold.
    Tool modules pass ``server.store``, so the process still has exactly one.

    ``operation`` is keyword-only and required: a lookup that cannot say what
    asked for the scene would log a failure nobody can act on. It comes from
    the closed set in :class:`~voxel_forge.scene_errors.SceneOperation`, so the
    value reaches the log as a known label rather than as free text.

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
        return scene_store.get(scene_name or None)
    except NoCurrentSceneError as exc:
        _LOG.info(
            "scene lookup failed operation=%s category=no_current_scene", operation
        )
        msg = "no scene yet — call voxelforge_create_scene first"
        raise KeyError(msg) from exc
    except UnknownSceneError as exc:
        _LOG.info("scene lookup failed operation=%s category=unknown_scene", operation)
        missing = scene_name
        msg = (
            f"scene '{missing}' is not loaded in this session — call "
            "voxelforge_load for a saved scene, or use the name of an "
            "existing session scene"
        )
        raise KeyError(msg) from exc


@contextlib.contextmanager
def _edit_scene(
    scene_name: str,
    *,
    operation: SceneOperation,
) -> cabc.Iterator[VoxelScene]:
    """Lock the entire edit and publish only after successful mutation.

    The lookup goes through :func:`resolve_scene` with the caller's
    ``operation``, so a failure inside an edit is logged under the tool that
    attempted it rather than under this wrapper. Without that, every editing
    tool's failures would be indistinguishable from one another in the log,
    which is precisely the signal the category alone cannot supply.
    """
    with store.lock:
        scene = resolve_scene(store, scene_name, operation=operation)
        has_completed = False
        try:
            yield scene
            has_completed = True
        finally:
            if has_completed:
                _sync_bridge(scene)


def _export_path(scene: VoxelScene, output_path: str, suffix: str) -> Path:
    """Resolve explicit destinations or the server's default export filename."""
    return (
        Path(output_path) if output_path else _exports_dir() / f"{scene.name}{suffix}"
    )


def main() -> None:
    """Run the MCP server on stdio, or print usage and exit for ``--help``.

    The editor bridge is opt-in: pass ``--bridge`` or set
    ``VOXELFORGE_BRIDGE=1`` to start its listener eagerly. Without either, no
    socket is bound until ``voxelforge_launch_editor`` asks for one, so a
    headless run stays headless.

    Notes
    -----
    Argument parsing happens before the bridge starts so that ``--help``
    answers and exits without binding a socket. ``argparse`` raises
    ``SystemExit`` for ``--help``, which is why the server is only reached once
    parsing returns.
    """
    import argparse
    import os

    parser = argparse.ArgumentParser(
        prog="voxel-forge-mcp",
        description=("VoxelForge MCP server (stdio transport) with an editor bridge."),
    )
    parser.add_argument(
        "--bridge",
        action="store_true",
        default=os.environ.get("VOXELFORGE_BRIDGE", "") == "1",
        help=(
            "start the editor bridge listener eagerly "
            "(default: only when the editor is launched; "
            "VOXELFORGE_BRIDGE=1 also enables it)"
        ),
    )
    args = parser.parse_args()
    if args.bridge:
        _ensure_bridge("server_start")
    # Report the state the bridge actually reached, not the one requested: an
    # eager start that failed would already have raised out of _ensure_bridge.
    _announce_startup(
        "eager" if args.bridge else "headless",
        "running" if current_ports() is not None else "down",
    )
    mcp.run(transport="stdio")


from .server_tools.build import (  # ruff: ignore[module-import-not-at-top-of-file]  # register after mcp exists
    voxelforge_build_chibi_bear,
    voxelforge_build_tree,
)
from .server_tools.io import (  # ruff: ignore[module-import-not-at-top-of-file]  # register after mcp exists
    voxelforge_export_obj,
    voxelforge_export_obj_legacy,
    voxelforge_export_roblox_merged,
    voxelforge_export_vox,
    voxelforge_import_vox,
    voxelforge_launch_editor,
    voxelforge_list_scenes,
    voxelforge_load,
    voxelforge_save,
)
from .server_tools.scene import (  # ruff: ignore[module-import-not-at-top-of-file]  # register after mcp exists
    voxelforge_about,
    voxelforge_add_layer,
    voxelforge_clear,
    voxelforge_create_scene,
    voxelforge_default_palette,
    voxelforge_fill_box,
    voxelforge_get_info,
    voxelforge_merge_stats,
    voxelforge_place_block,
    voxelforge_place_many,
    voxelforge_preview,
    voxelforge_remove_block,
    voxelforge_select_scene,
    voxelforge_set_active_layer,
    voxelforge_set_palette,
    voxelforge_set_voxel_size,
)

__all__ = [
    "MAX_BLOCKS_JSON_CHARS",
    "MAX_TOOL_VOXELS",
    "SceneStore",
    "main",
    "mcp",
    "store",
    "voxelforge_about",
    "voxelforge_add_layer",
    "voxelforge_build_chibi_bear",
    "voxelforge_build_tree",
    "voxelforge_clear",
    "voxelforge_create_scene",
    "voxelforge_default_palette",
    "voxelforge_export_obj",
    "voxelforge_export_obj_legacy",
    "voxelforge_export_roblox_merged",
    "voxelforge_export_vox",
    "voxelforge_fill_box",
    "voxelforge_get_info",
    "voxelforge_import_vox",
    "voxelforge_launch_editor",
    "voxelforge_list_scenes",
    "voxelforge_load",
    "voxelforge_merge_stats",
    "voxelforge_place_block",
    "voxelforge_place_many",
    "voxelforge_preview",
    "voxelforge_remove_block",
    "voxelforge_save",
    "voxelforge_select_scene",
    "voxelforge_set_active_layer",
    "voxelforge_set_palette",
    "voxelforge_set_voxel_size",
]

if __name__ == "__main__":
    main()
