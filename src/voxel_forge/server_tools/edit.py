"""Edit MCP tools using the shared lock-owning server registry."""

from __future__ import annotations

from voxel_forge import server
from voxel_forge.scene_boundary import SceneOperation


@server.mcp.tool()
# pylint: disable-next=too-many-arguments,too-many-positional-arguments  # MCP schema
def voxelforge_place_block(  # ruff: ignore[too-many-arguments, too-many-positional-arguments]  # MCP tool schema
    x: int,
    y: int,
    z: int,
    color: str = "1",
    scene_name: str = "",
) -> str:
    """
    Place a single voxel at grid coordinates (x,y,z).

    Parameters
    ----------
    x, y, z : int
        Grid coordinates of the voxel.
    color : str, optional
        Palette key or ``#RRGGBB`` code; defaults to ``"1"``.
    scene_name : str, optional
        Name of the target scene; defaults to the current scene.

    Returns
    -------
    str
        A confirmation message with the total block count.

    Raises
    ------
    ValueError
        If ``color`` is neither a palette key nor a valid ``#RRGGBB`` code.
    KeyError
        If the target scene is not found.

    Notes
    -----
    A failed call does not modify the scene, because the colour is validated
    before any block is placed.
    """
    with server._edit_scene(scene_name, operation=SceneOperation.PLACE_BLOCK) as scene:
        scene.place(x, y, z, color)
        total = scene.block_count()
        return f"placed ({x},{y},{z}) colour '{color}' — {total} blocks total"


@server.mcp.tool()
def voxelforge_place_many(blocks_json: str, scene_name: str = "") -> str:
    """
    Place many voxels from a JSON array.

    Parameters
    ----------
    blocks_json : str
        JSON array of ``[x, y, z, colour]`` rows, for example
        ``[[0,0,0,"1"], [1,0,0,"2"]]``. Colours may be palette keys or
        ``#RRGGBB`` codes. At most ``MAX_TOOL_VOXELS`` rows are supported.
    scene_name : str, optional
        Name of the target scene; defaults to the current scene.

    Returns
    -------
    str
        A confirmation message with the number of voxels placed and the total
        block count.

    Raises
    ------
    ValueError
        If the payload exceeds its bounds, is not a JSON array, holds
        oversized or malformed rows, or carries a colour that cannot be
        resolved.
    json.JSONDecodeError
        If ``blocks_json`` is not valid JSON.
    KeyError
        If the target scene is not found.

    Notes
    -----
    Every colour is validated before the first block is placed, so a failed
    call does not modify the scene.
    """
    blocks = server._parse_blocks_json(blocks_json)
    with server.store.lock:
        scene = server.resolve_scene(
            server.store, scene_name, operation=SceneOperation.PLACE_MANY
        )
        for _x, _y, _z, color in blocks:
            scene.resolve_color(color)
        for x, y, z, color in blocks:
            scene.place(x, y, z, color)
        server._sync_bridge(scene)
        return (
            "placed "
            f"{len(blocks)}"
            " voxels in '"
            f"{scene.name}"
            "' — "
            f"{scene.block_count()}"
            " blocks total"
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
    """
    Fill a 3D box (well suited to bases, bodies and walls).

    Parameters
    ----------
    x1, x2, y1, y2, z1, z2 : int
        Inclusive bounds on each axis; the order of each pair does not matter.
    color : str, optional
        Palette key or ``#RRGGBB`` code; defaults to ``"1"``.
    scene_name : str, optional
        Name of the target scene; defaults to the current scene.

    Returns
    -------
    str
        A confirmation message with the number of voxels filled and the total
        block count.

    Raises
    ------
    ValueError
        If the volume exceeds ``MAX_TOOL_VOXELS``, or ``color`` cannot be
        resolved.
    KeyError
        If the target scene is not found.

    Notes
    -----
    The bounds are validated before filling, so a failed call does not modify
    the scene.
    """
    with server.store.lock:
        scene = server.resolve_scene(
            server.store, scene_name, operation=SceneOperation.FILL_BOX
        )
        volume = (abs(x2 - x1) + 1) * (abs(y2 - y1) + 1) * (abs(z2 - z1) + 1)
        if volume > server.MAX_TOOL_VOXELS:
            msg = (
                f"fill_box supports at most {server.MAX_TOOL_VOXELS:,} voxels per call"
            )
            raise ValueError(msg)
        n = scene.fill_box(x1, x2, y1, y2, z1, z2, color)
        server._sync_bridge(scene)
        return (
            f"filled {n} voxels with colour '{color}' — "
            f"{scene.block_count()} blocks total"
        )


@server.mcp.tool()
def voxelforge_remove_block(x: int, y: int, z: int, scene_name: str = "") -> str:
    """
    Remove the voxel at the given coordinates.

    Parameters
    ----------
    x, y, z : int
        Grid coordinates of the voxel.
    scene_name : str, optional
        Name of the target scene; defaults to the current scene.

    Returns
    -------
    str
        ``"removed"`` on success, or ``"no voxel there"`` when the coordinates
        are empty.

    Raises
    ------
    KeyError
        If the target scene is not found.

    Notes
    -----
    When the coordinates are empty no ``scene_update`` is announced, because
    the scene did not change.
    """
    with server.store.lock:
        scene = server.resolve_scene(
            server.store, scene_name, operation=SceneOperation.REMOVE_BLOCK
        )
        ok = scene.remove(x, y, z)
        if ok:
            server._sync_bridge(scene)
        return "removed" if ok else "no voxel there"


@server.mcp.tool()
def voxelforge_clear(scene_name: str = "") -> str:
    """
    Clear every voxel in every layer.

    Parameters
    ----------
    scene_name : str, optional
        Name of the target scene; defaults to the current scene.

    Returns
    -------
    str
        A confirmation message with the scene name.

    Raises
    ------
    KeyError
        If the target scene is not found.
    """
    with server.store.lock:
        scene = server.resolve_scene(
            server.store, scene_name, operation=SceneOperation.CLEAR
        )
        scene.clear()
        server._sync_bridge(scene)
        return f"cleared scene '{scene.name}'"
