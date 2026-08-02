"""MCP Server — VoxelForge (Goxel-inspired) for Cursor, Claude, and other AI clients."""

from __future__ import annotations

import json
import typing as typ
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .bridge import current_ports, notify_scene_update, start_bridge_background
from .bridge import store as bridge_store
from .model import SceneStore

if typ.TYPE_CHECKING:
    from .model import VoxelScene

mcp = FastMCP(
    "VoxelForge",
    instructions=(
        "VoxelForge — a Goxel-style 3D voxel builder "
        "(24-bit RGB, layers, .vox/.obj export).\n"
        "Workflow: voxelforge_create_scene → "
        "voxelforge_place_many / voxelforge_fill_box → "
        "voxelforge_preview → voxelforge_export_vox or voxelforge_export_obj\n"
        "Open the 3D editor: voxelforge_launch_editor\n"
        "MagicaVoxel (.vox) files, as used by Goxel, can be imported"
    ),
)

store = SceneStore()
MAX_TOOL_VOXELS = 100_000


def _ensure_bridge() -> None:
    """Start the editor bridge and point it at the server's scene store."""
    start_bridge_background()
    bridge_store._scenes = store._scenes
    bridge_store._current = store._current


def _sync_bridge(scene: VoxelScene) -> None:
    """Notify bridge subscribers when a bridge is running.

    Scene mutations must not start the bridge: a headless or sandboxed
    run should never bind a port. The bridge starts only when an editor
    is requested (`voxelforge_launch_editor`) or when the server is run
    with `--bridge`.

    Parameters
    ----------
    scene
        The scene whose contents changed.
    """
    if current_ports() is None:
        return
    bridge_store._scenes = store._scenes
    bridge_store._current = store._current
    notify_scene_update(scene)


def _coerce_block_row(row: object) -> tuple[int, int, int, str]:
    """Coerce one block row, array or object shaped, into a tuple.

    Parameters
    ----------
    row
        Either an ``[x, y, z, colour]`` array or an object with ``x``,
        ``y``, ``z`` and ``color`` (or ``colour``) members.

    Raises
    ------
    ValueError
        If the row matches neither shape or its values do not coerce.
    """
    msg = f"malformed block row: {row!r}"
    match row:
        case (
            [x, y, z, color, *_]
            | {"x": x, "y": y, "z": z, "color": color}
            | {"x": x, "y": y, "z": z, "colour": color}
        ):
            try:
                return (int(x), int(y), int(z), str(color))
            except (TypeError, ValueError) as exc:
                raise ValueError(msg) from exc
        case _:
            raise ValueError(msg)


def _parse_blocks_json(blocks_json: str) -> list[tuple[int, int, int, str]]:
    """Decode a JSON array of block rows into coordinate and colour tuples.

    Parameters
    ----------
    blocks_json
        A JSON array whose rows are either ``[x, y, z, colour]`` arrays
        or objects such as ``{"x": 1, "y": 2, "z": 3, "color": "#RRGGBB"}``
        (``colour`` is accepted too). Shapes may be mixed freely.

    Returns
    -------
    list of tuple
        The decoded rows.

    Raises
    ------
    ValueError
        If the payload is not an array, exceeds the per-call voxel budget, or
        contains a malformed row.
    """
    data = json.loads(blocks_json)
    if not isinstance(data, list):
        msg = "blocks must be a JSON array"
        raise ValueError(msg)  # ruff: ignore[type-check-without-type-error]  # ValueError is the tool contract
    if len(data) > MAX_TOOL_VOXELS:
        msg = f"place_many supports at most {MAX_TOOL_VOXELS:,} voxels per call"
        raise ValueError(msg)
    return [_coerce_block_row(row) for row in data]


def _exports_dir() -> Path:
    """Return the export directory, creating it when absent.

    Returns
    -------
    pathlib.Path
        The ``~/.voxel-forge/exports`` directory.
    """
    root = Path.home() / ".voxel-forge" / "exports"
    root.mkdir(parents=True, exist_ok=True)
    return root


def main() -> None:
    """Run the VoxelForge MCP server over the stdio transport.

    The editor bridge is opt-in: pass ``--bridge`` or set
    ``VOXELFORGE_BRIDGE=1`` to start its listener eagerly. Without it,
    no socket is bound until ``voxelforge_launch_editor`` asks for one.
    """
    import argparse
    import os

    parser = argparse.ArgumentParser(
        prog="voxel-forge-mcp",
        description="VoxelForge MCP server (stdio transport) with an editor bridge.",
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
        _ensure_bridge()
    mcp.run(transport="stdio")


from voxel_forge.server_tools.build import (  # ruff: ignore[module-import-not-at-top-of-file]  # register after mcp exists
    voxelforge_build_chibi_bear,
    voxelforge_build_tree,
)
from voxel_forge.server_tools.io import (  # ruff: ignore[module-import-not-at-top-of-file]  # register after mcp exists
    voxelforge_export_obj,
    voxelforge_export_obj_legacy,
    voxelforge_export_roblox_merged,
    voxelforge_export_vox,
    voxelforge_import_vox,
    voxelforge_launch_editor,
    voxelforge_merge_stats,
)
from voxel_forge.server_tools.scene import (  # ruff: ignore[module-import-not-at-top-of-file]  # register after mcp exists
    voxelforge_about,
    voxelforge_add_layer,
    voxelforge_clear,
    voxelforge_create_scene,
    voxelforge_default_palette,
    voxelforge_fill_box,
    voxelforge_get_info,
    voxelforge_list_scenes,
    voxelforge_load,
    voxelforge_place_block,
    voxelforge_place_many,
    voxelforge_preview,
    voxelforge_remove_block,
    voxelforge_save,
    voxelforge_select_scene,
    voxelforge_set_active_layer,
    voxelforge_set_palette,
    voxelforge_set_voxel_size,
)

__all__ = [
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
