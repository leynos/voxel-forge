"""Scene, layer, palette and persistence MCP tools.

Mutable server state is reached through the :mod:`voxel_forge.server` module
object rather than by importing its attributes, so tests that replace
``server.store`` or ``server._sync_bridge`` observe the substitution.
"""

import json

from voxel_forge import server
from voxel_forge.model import DEFAULT_PALETTE, VoxelScene
from voxel_forge.preview import summary


@server.mcp.tool()
def voxelforge_about() -> str:
    """Describe VoxelForge and its relationship to Goxel."""
    return (
        "VoxelForge — a voxel editor built on the ideas of Goxel "
        "(https://github.com/guillaumechereau/goxel)\n"
        "Features: 24-bit RGB, layers, unbounded scenes, "
        ".vox (MagicaVoxel) and .obj export\n"
        "The MCP server works with Cursor, Claude Desktop, "
        "and any other client that supports the Model Context Protocol\n"
        "The original Goxel is GPL-3.0 — VoxelForge is a new, "
        "MCP-first implementation"
    )


@server.mcp.tool()
def voxelforge_create_scene(name: str) -> str:
    """Create a new voxel scene."""
    scene = server.store.create(name)
    server._sync_bridge(scene)
    return f"Created scene '{scene.name}' (default layer: {scene.layers[0].name})"


@server.mcp.tool()
def voxelforge_select_scene(name: str) -> str:
    """Select the scene being edited."""
    scene = server.store.set_current(name)
    server._sync_bridge(scene)
    return f"Selected scene '{scene.name}' ({scene.block_count()} blocks)"


@server.mcp.tool()
def voxelforge_add_layer(name: str, scene_name: str = "") -> str:
    """Add a new layer, as Goxel does."""
    scene = server.store.get(scene_name or None)
    layer = scene.add_layer(name)
    server._sync_bridge(scene)
    return (
        f"Added layer '{layer.name}' to '{scene.name}' — "
        f"{len(scene.layers)} layers in total"
    )


@server.mcp.tool()
def voxelforge_set_active_layer(index: int, scene_name: str = "") -> str:
    """Set the active layer, indexed from zero."""
    scene = server.store.get(scene_name or None)
    if index < 0 or index >= len(scene.layers):
        msg = f"layer index must lie between 0 and {len(scene.layers) - 1}"
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
    """Define a colour in the palette as 24-bit RGB."""
    scene = server.store.get(scene_name or None)
    scene.set_palette_color(color_key, r, g, b)
    server._sync_bridge(scene)
    return f"Palette {color_key} = RGB({r},{g},{b})"


@server.mcp.tool()
# pylint: disable-next=too-many-arguments,too-many-positional-arguments  # MCP schema
def voxelforge_place_block(  # ruff: ignore[too-many-arguments, too-many-positional-arguments]  # MCP tool schema
    x: int,
    y: int,
    z: int,
    color: str = "1",
    scene_name: str = "",
) -> str:
    """Place a single voxel at the coordinate (x, y, z)."""
    scene = server.store.get(scene_name or None)
    scene.place(x, y, z, color)
    server._sync_bridge(scene)
    return (
        f"Placed ({x},{y},{z}) in colour '{color}' — "
        f"{scene.block_count()} blocks in total"
    )


@server.mcp.tool()
def voxelforge_place_many(blocks_json: str, scene_name: str = "") -> str:
    """
    Place many voxels from a JSON array of [x,y,z,colour] rows.

    Example: [[1,0,0,"#3CB043"], [2,0,0,"2"]], where the colour is either
    a palette index ("2") or #RRGGBB. Object rows are also accepted:
    {"x":1,"y":0,"z":0,"color":"#3CB043"}.
    """
    scene = server.store.get(scene_name or None)
    blocks = server._parse_blocks_json(blocks_json)
    for _x, _y, _z, color in blocks:
        scene.resolve_color(color)
    for x, y, z, color in blocks:
        scene.place(x, y, z, color)
    server._sync_bridge(scene)
    return (
        f"Placed {len(blocks)} voxels in '{scene.name}' — "
        f"{scene.block_count()} blocks in total"
    )


@server.mcp.tool()
# pylint: disable-next=too-many-arguments,too-many-positional-arguments  # MCP schema
def voxelforge_fill_box(  # ruff: ignore[too-many-arguments, too-many-positional-arguments]  # MCP tool schema
    x1: int,
    x2: int,
    y1: int,
    y2: int,
    z1: int,
    z2: int,
    color: str = "1",
    scene_name: str = "",
) -> str:
    """Fill a 3D box, suited to bases, building shells and walls."""
    scene = server.store.get(scene_name or None)
    volume = (abs(x2 - x1) + 1) * (abs(y2 - y1) + 1) * (abs(z2 - z1) + 1)
    if volume > server.MAX_TOOL_VOXELS:
        msg = f"fill_box supports at most {server.MAX_TOOL_VOXELS:,} voxels per call"
        raise ValueError(msg)
    n = scene.fill_box(x1, x2, y1, y2, z1, z2, color)
    server._sync_bridge(scene)
    return (
        f"Filled {n} voxels in colour '{color}' — {scene.block_count()} blocks in total"
    )


@server.mcp.tool()
def voxelforge_remove_block(x: int, y: int, z: int, scene_name: str = "") -> str:
    """Remove the voxel at a coordinate."""
    scene = server.store.get(scene_name or None)
    ok = scene.remove(x, y, z)
    if ok:
        server._sync_bridge(scene)
    return "Removed" if ok else "There is no voxel at that coordinate"


@server.mcp.tool()
def voxelforge_clear(scene_name: str = "") -> str:
    """Clear every voxel from the scene."""
    scene = server.store.get(scene_name or None)
    scene.clear()
    server._sync_bridge(scene)
    return f"Cleared scene '{scene.name}'"


@server.mcp.tool()
def voxelforge_preview(scene_name: str = "") -> str:
    """Show a summary and an ASCII view of each Y slice, for checking shape."""
    scene = server.store.get(scene_name or None)
    return summary(scene)


@server.mcp.tool()
def voxelforge_get_info(scene_name: str = "") -> str:
    """Return the scene's details as JSON."""
    scene = server.store.get(scene_name or None)
    return json.dumps(scene.to_dict(), ensure_ascii=False, indent=2)


@server.mcp.tool()
def voxelforge_save(scene_name: str = "") -> str:
    """Save the scene to ~/.voxel-forge/scenes/."""
    scene = server.store.get(scene_name or None)
    path = scene.save()
    return f"Saved '{scene.name}' to {path}"


@server.mcp.tool()
def voxelforge_load(name: str) -> str:
    """Load a scene from a file."""
    scene = VoxelScene.load(name)
    server.store._scenes[name] = scene
    server.store._current = name
    server._sync_bridge(scene)
    return f"Loaded '{name}' ({scene.block_count()} blocks)"


@server.mcp.tool()
def voxelforge_list_scenes() -> str:
    """List the scenes in this session and those saved to disk."""
    return json.dumps(
        {
            "active_session": server.store.list_active(),
            "saved_on_disk": VoxelScene.list_saved(),
        },
        ensure_ascii=False,
        indent=2,
    )


@server.mcp.tool()
def voxelforge_set_voxel_size(size: float, scene_name: str = "") -> str:
    """Set the voxel size in world units.

    1.0 is the normal size; 0.25 is four times finer.
    """
    scene = server.store.get(scene_name or None)
    scene.voxel_size = max(0.05, min(2.0, float(size)))
    server._sync_bridge(scene)
    return f"Set voxel_size={scene.voxel_size} in '{scene.name}'"


@server.mcp.tool()
def voxelforge_default_palette() -> str:
    """Return the default colour palette."""
    return json.dumps({k: list(v) for k, v in DEFAULT_PALETTE.items()}, indent=2)
