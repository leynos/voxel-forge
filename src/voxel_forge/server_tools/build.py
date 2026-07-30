"""Procedural model-building MCP tools.

Mutable server state is reached through the :mod:`voxel_forge.server` module
object rather than by importing its attributes, so tests that replace
``server.store`` or ``server._sync_bridge`` observe the substitution.
"""

from voxel_forge import server
from voxel_forge.procedural import build_chibi_bear, build_tree


@server.mcp.tool()
def voxelforge_build_chibi_bear(name: str = "chibi_bear", resolution: int = 3) -> str:
    """สร้างรูปปั้นหมี chibi (resolution 2-4 แนะนำ)."""
    scene = build_chibi_bear(name=name, resolution=resolution)
    server.store._scenes[scene.name] = scene
    server.store._current = scene.name
    server._sync_bridge(scene)
    return (
        f"สร้างหมี chibi '{scene.name}' — {scene.block_count()} voxels "
        f"(resolution {resolution})"
    )


@server.mcp.tool()
def voxelforge_build_tree(name: str = "tree", resolution: int = 4) -> str:
    """
    สร้างต้นไม้ procedural ความละเอียดปรับได้.

    resolution: 1=หยาบ, 2=ปานกลาง, 4=ละเอียด (แนะนำ), 8=สูงมาก.
    """
    scene = build_tree(name=name, resolution=resolution)
    server.store._scenes[scene.name] = scene
    server.store._current = scene.name
    server._sync_bridge(scene)
    vs = scene.voxel_size
    return (
        f"สร้างต้นไม้ '{scene.name}' — {scene.block_count()} voxels, "
        f"voxel_size={vs} (resolution {resolution}x)\n"
        f"เปิด editor เพื่อดู 3D หรือ voxelforge_preview ตรวจ ASCII"
    )
