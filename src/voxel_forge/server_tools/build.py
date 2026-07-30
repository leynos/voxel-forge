"""Procedural model-building MCP tools.

Mutable server state is reached through the :mod:`voxel_forge.server` module
object rather than by importing its attributes, so tests that replace
``server.store`` or ``server._sync_bridge`` observe the substitution.
"""

from voxel_forge import server
from voxel_forge.procedural import build_chibi_bear, build_tree


@server.mcp.tool()
def voxelforge_build_chibi_bear(name: str = "chibi_bear", resolution: int = 3) -> str:
    """Build a chibi bear figurine.

    A resolution of 2 to 4 is recommended.
    """
    scene = build_chibi_bear(name=name, resolution=resolution)
    server.store._scenes[scene.name] = scene
    server.store._current = scene.name
    server._sync_bridge(scene)
    return (
        f"Built chibi bear '{scene.name}' — {scene.block_count()} voxels "
        f"(resolution {resolution})"
    )


@server.mcp.tool()
def voxelforge_build_tree(name: str = "tree", resolution: int = 4) -> str:
    """
    Build a procedural tree at an adjustable resolution.

    resolution: 1=coarse, 2=medium, 4=fine (recommended), 8=very fine.
    """
    scene = build_tree(name=name, resolution=resolution)
    server.store._scenes[scene.name] = scene
    server.store._current = scene.name
    server._sync_bridge(scene)
    vs = scene.voxel_size
    return (
        f"Built tree '{scene.name}' — {scene.block_count()} voxels, "
        f"voxel_size={vs} (resolution {resolution}x)\n"
        f"Open the editor for a 3D view, or use voxelforge_preview "
        f"for an ASCII check"
    )
