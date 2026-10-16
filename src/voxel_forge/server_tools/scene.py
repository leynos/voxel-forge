"""Scene MCP tools using the shared lock-owning server registry."""

from __future__ import annotations

import json

from voxel_forge import server

from .edit import voxelforge_clear as voxelforge_clear
from .edit import voxelforge_fill_box as voxelforge_fill_box
from .edit import voxelforge_place_block as voxelforge_place_block
from .edit import voxelforge_place_many as voxelforge_place_many
from .edit import voxelforge_remove_block as voxelforge_remove_block


@server.mcp.tool()
def voxelforge_about() -> str:
    """Describe VoxelForge and its relationship to Goxel."""
    return (
        "VoxelForge — a voxel editor inspired by Goxel "
        "(https://github.com/guillaumechereau/goxel)\n"
        "Features: 24-bit RGB, layers, unlimited scene size, export .vox "
        "(MagicaVoxel) and .obj\n"
        "MCP works with Cursor, Claude Desktop, and any other client that "
        "supports the Model Context Protocol\n"
        "Goxel itself is GPL-3.0 — VoxelForge is a new, MCP-first "
        "implementation"
    )


@server.mcp.tool()
def voxelforge_create_scene(name: str) -> str:
    """Create a new voxel scene.

    Parameters
    ----------
    name : str
        Scene name, usable as a filename. Must be 1-80 characters, and must
        contain no path separators or control characters.

    Returns
    -------
    str
        A confirmation message with the scene name and its initial layer.

    Raises
    ------
    ValueError
        If the scene name is not safe to use as a filename.

    Notes
    -----
    A new scene is not written to disk yet; call ``voxelforge_save`` when you
    want it persisted.
    """
    with server.store.lock:
        scene = server.store.create(name)
        server._sync_bridge(scene)
        return f"Created scene '{scene.name}' (initial layer: {scene.layers[0].name})"


@server.mcp.tool()
def voxelforge_select_scene(name: str) -> str:
    """Select the scene being edited.

    Parameters
    ----------
    name : str
        Name of a scene already loaded in this session.

    Returns
    -------
    str
        A confirmation message with the scene's block count.

    Raises
    ------
    KeyError
        If no scene with this name is in the session; the message names
        ``voxelforge_load`` and the alternative of an existing scene name.
    """
    with server.store.lock:
        # The lookup goes through ``resolve_scene`` rather than
        # ``store.select`` so this tool reports a mistyped name the same way
        # every other tool does. Selecting is the operation that *only* names a
        # scene, so it is the likeliest place for a caller to hit this error
        # first; leaving it on the domain's transport-neutral message would
        # make the recovery instruction depend on which tool was called.
        # ``store.lock`` is reentrant, so resolving inside it costs nothing.
        server.resolve_scene(name)
        scene = server.store.select(name)
        server._sync_bridge(scene)
        return f"Selected scene '{scene.name}' ({scene.block_count()} blocks)"


@server.mcp.tool()
def voxelforge_add_layer(name: str, scene_name: str = "") -> str:
    """Add a new layer (as in Goxel).

    Parameters
    ----------
    name : str
        Name of the layer, shown in the editor and preview.
    scene_name : str, optional
        Name of the target scene; defaults to the current scene.

    Returns
    -------
    str
        A confirmation message with the total layer count.

    Raises
    ------
    KeyError
        If the target scene is not found.
    """
    with server.store.lock:
        scene = server.resolve_scene(scene_name)
        layer = scene.add_layer(name)
        server._sync_bridge(scene)
        return (
            "Added layer '"
            f"{layer.name}"
            "' to '"
            f"{scene.name}"
            "' — "
            f"{len(scene.layers)}"
            " layers in total"
        )


@server.mcp.tool()
def voxelforge_set_active_layer(index: int, scene_name: str = "") -> str:
    """Set the active layer (0-based index).

    Parameters
    ----------
    index : int
        Layer index, counted from 0.
    scene_name : str, optional
        Name of the target scene; defaults to the current scene.

    Returns
    -------
    str
        A confirmation message with the selected layer's name.

    Raises
    ------
    ValueError
        If ``index`` is outside the range of existing layers.
    KeyError
        If the target scene is not found.
    """
    with server.store.lock:
        scene = server.resolve_scene(scene_name)
        if index < 0 or index >= len(scene.layers):
            msg = f"layer index must be within 0..{len(scene.layers) - 1}"
            raise ValueError(msg)
        scene.active_layer = index
        server._sync_bridge(scene)
        return f"active layer = {scene.layers[index].name}"


@server.mcp.tool()
# pylint: disable-next=too-many-arguments,too-many-positional-arguments  # MCP schema
def voxelforge_set_palette(  # ruff: ignore[too-many-arguments, too-many-positional-arguments]  # MCP tool schema
    color_key: str,
    r: int,
    g: int,
    b: int,
    scene_name: str = "",
) -> str:
    """Set a palette colour (24-bit RGB).

    Parameters
    ----------
    color_key : str
        Key of the colour to set or overwrite.
    r, g, b : int
        Channel values, each an integer 0-255 (floats and numeric strings are
        not accepted).
    scene_name : str, optional
        Name of the target scene; defaults to the current scene.

    Returns
    -------
    str
        A confirmation message with the colour that was set.

    Raises
    ------
    ValueError
        If any value is not an integer in the 0-255 range.
    KeyError
        If the target scene is not found.
    """
    with server._edit_scene(scene_name) as scene:
        scene.set_palette_color(color_key, r, g, b)
        return f"palette {color_key} = RGB({r},{g},{b})"


@server.mcp.tool()
def voxelforge_preview(scene_name: str = "") -> str:
    """Show a summary plus an ASCII view of each Y slice (for shape checking).

    Parameters
    ----------
    scene_name : str, optional
        Name of the target scene; defaults to the current scene.

    Returns
    -------
    str
        A summary message and an ASCII rendering of the scene.

    Raises
    ------
    KeyError
        If the target scene is not found.
    """
    with server.store.lock:
        scene = server.resolve_scene(scene_name)
        return server.summary(scene)


@server.mcp.tool()
def voxelforge_get_info(scene_name: str = "") -> str:
    """Scene information as JSON.

    Parameters
    ----------
    scene_name : str, optional
        Name of the target scene; defaults to the current scene.

    Returns
    -------
    str
        JSON of ``VoxelScene.to_dict()`` (name, voxel_size, palette, layers).

    Raises
    ------
    KeyError
        If the target scene is not found.

    Notes
    -----
    Read-only: it does not modify the scene and announces no ``scene_update``.
    """
    with server.store.lock:
        scene = server.resolve_scene(scene_name)
        return json.dumps(scene.to_dict(), ensure_ascii=False, indent=2)


@server.mcp.tool()
def voxelforge_merge_stats(scene_name: str = "") -> str:
    """See how much merging voxels into boxes saves before exporting.

    Parameters
    ----------
    scene_name : str, optional
        Name of the target scene; defaults to the current scene.

    Returns
    -------
    str
        Voxel count, box count after merging, and the percentage reduction.

    Raises
    ------
    KeyError
        If the target scene is not found.
    """
    with server.store.lock:
        scene = server.resolve_scene(scene_name)
        stats = server.merge_stats(scene)
        return (
            f"Scene '{scene.name}':\n"
            f"  voxels (after deduping overlaps): {stats['voxels']}\n"
            f"  merged boxes (parts): {stats['merged_boxes']}\n"
            f"  saved: {stats['parts_saved']} ({stats['reduction_percent']}%)"
        )


@server.mcp.tool()
def voxelforge_set_voxel_size(size: float, scene_name: str = "") -> str:
    """Set the voxel size in world units (1.0=normal, 0.25=4x finer).

    Parameters
    ----------
    size : float
        Size of one grid cell; clamped to the range 0.05-2.0.
    scene_name : str, optional
        Name of the target scene; defaults to the current scene.

    Returns
    -------
    str
        A confirmation message with the voxel_size actually applied.

    Raises
    ------
    KeyError
        If the target scene is not found.
    """
    with server.store.lock:
        scene = server.resolve_scene(scene_name)
        scene.voxel_size = max(0.05, min(2.0, float(size)))
        server._sync_bridge(scene)
        return f"set voxel_size={scene.voxel_size} in '{scene.name}'"


@server.mcp.tool()
def voxelforge_default_palette() -> str:
    """Return the default colour palette.

    Returns
    -------
    str
        JSON of the default palette (key → [r, g, b]).
    """
    return json.dumps({k: list(v) for k, v in server.DEFAULT_PALETTE.items()}, indent=2)
