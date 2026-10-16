"""Build MCP tools using the shared lock-owning server registry."""

from __future__ import annotations

from voxel_forge import server


@server.mcp.tool()
def voxelforge_build_tree(name: str = "tree", resolution: int = 4) -> str:
    """Build a procedural tree at an adjustable resolution.

    resolution: 1=coarse, 2=medium, 4=fine (recommended), 8=very high

    Parameters
    ----------
    name : str, optional
        Name of the scene to create.
    resolution : int, optional
        Resolution of the model.

    Returns
    -------
    str
        A confirmation message with the voxel count and voxel_size.
    """
    scene = server.build_tree(name=name, resolution=resolution)
    with server.store.lock:
        server.store.register(scene)
        server._sync_bridge(scene)
        vs = scene.voxel_size
        return (
            f"Built tree '{scene.name}' — {scene.block_count()} voxels, "
            f"voxel_size={vs} (resolution {resolution}x)\n"
            f"Open the editor to view it in 3D, or run voxelforge_preview "
            f"for an ASCII check"
        )


@server.mcp.tool()
def voxelforge_build_chibi_bear(name: str = "chibi_bear", resolution: int = 3) -> str:
    """Build a chibi bear statue (resolution 2-4 recommended).

    Parameters
    ----------
    name : str, optional
        Name of the scene to create.
    resolution : int, optional
        Resolution of the model.

    Returns
    -------
    str
        A confirmation message with the voxel count.
    """
    scene = server.build_chibi_bear(name=name, resolution=resolution)
    with server.store.lock:
        server.store.register(scene)
        server._sync_bridge(scene)
        return (
            "Built chibi bear '"
            f"{scene.name}"
            "' — "
            f"{scene.block_count()}"
            " voxels (resolution "
            f"{resolution}"
            ")"
        )
