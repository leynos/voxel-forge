"""Build MCP tools using the shared lock-owning server registry."""

from __future__ import annotations

from voxel_forge import server


@server.mcp.tool()
def voxelforge_build_tree(name: str = "tree", resolution: int = 4) -> str:
    """สร้างต้นไม้ procedural ความละเอียดปรับได้.

    resolution: 1=หยาบ, 2=ปานกลาง, 4=ละเอียด (แนะนำ), 8=สูงมาก

    Parameters
    ----------
    name : str, optional
        ชื่อ scene ที่สร้าง
    resolution : int, optional
        ความละเอียดของโมเดล

    Returns
    -------
    str
        ข้อความยืนยันพร้อมจำนวน voxel และ voxel_size
    """
    scene = server.build_tree(name=name, resolution=resolution)
    with server.store.lock:
        server.store.register(scene)
        server._sync_bridge(scene)
        vs = scene.voxel_size
        return (
            f"สร้างต้นไม้ '{scene.name}' — {scene.block_count()} voxels, "
            f"voxel_size={vs} (resolution {resolution}x)\n"
            f"เปิด editor เพื่อดู 3D หรือ voxelforge_preview ตรวจ ASCII"
        )


@server.mcp.tool()
def voxelforge_build_chibi_bear(name: str = "chibi_bear", resolution: int = 3) -> str:
    """สร้างรูปปั้นหมี chibi (resolution 2-4 แนะนำ).

    Parameters
    ----------
    name : str, optional
        ชื่อ scene ที่สร้าง
    resolution : int, optional
        ความละเอียดของโมเดล

    Returns
    -------
    str
        ข้อความยืนยันพร้อมจำนวน voxel
    """
    scene = server.build_chibi_bear(name=name, resolution=resolution)
    with server.store.lock:
        server.store.register(scene)
        server._sync_bridge(scene)
        return (
            "สร้างหมี chibi '"
            f"{scene.name}"
            "' — "
            f"{scene.block_count()}"
            " voxels (resolution "
            f"{resolution}"
            ")"
        )
