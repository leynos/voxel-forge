"""Edit MCP tools using the shared lock-owning server registry."""

from __future__ import annotations

from voxel_forge import server


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
    วาง voxel 1 ลูกที่พิกัด (x,y,z).

    Parameters
    ----------
    x, y, z : int
        พิกัดกริดของ voxel
    color : str, optional
        คีย์พาเลตหรือรหัส ``#RRGGBB`` ค่าเริ่มต้น ``"1"``
    scene_name : str, optional
        ชื่อ scene เป้าหมาย ค่าเริ่มต้นคือ scene ปัจจุบัน

    Returns
    -------
    str
        ข้อความยืนยันพร้อมจำนวนบล็อกรวม

    Raises
    ------
    ValueError
        ถ้า ``color`` ไม่ใช่คีย์พาเลตหรือรหัส ``#RRGGBB`` ที่ถูกต้อง
    KeyError
        ถ้าไม่พบ scene เป้าหมาย

    Notes
    -----
    การเรียกที่ล้มเหลวไม่แก้ไข scene เพราะสีถูกตรวจสอบก่อนวางบล็อก
    """
    with server._edit_scene(scene_name) as scene:
        scene.place(x, y, z, color)
        return f"วาง ({x},{y},{z}) สี '{color}' — รวม {scene.block_count()} บล็อก"


@server.mcp.tool()
def voxelforge_place_many(blocks_json: str, scene_name: str = "") -> str:
    """
    วางหลาย voxel จาก JSON array.

    Parameters
    ----------
    blocks_json : str
        JSON array ของแถว ``[x, y, z, สี]`` เช่น ``[[0,0,0,"1"], [1,0,0,"2"]]``
        สีใช้คีย์พาเลตหรือรหัส ``#RRGGBB`` ได้ รองรับไม่เกิน ``MAX_TOOL_VOXELS`` แถว
    scene_name : str, optional
        ชื่อ scene เป้าหมาย ค่าเริ่มต้นคือ scene ปัจจุบัน

    Returns
    -------
    str
        ข้อความยืนยันพร้อมจำนวน voxel ที่วางและจำนวนบล็อกรวม

    Raises
    ------
    ValueError
        ถ้า payload ใหญ่เกินขอบเขต ไม่ใช่ JSON array มีแถวเกินขอบเขต แถวผิดรูปแบบ
        หรือมีสีที่ resolve ไม่ได้
    json.JSONDecodeError
        ถ้า ``blocks_json`` ไม่ใช่ JSON ที่ถูกต้อง
    KeyError
        ถ้าไม่พบ scene เป้าหมาย

    Notes
    -----
    ทุกสีถูกตรวจสอบก่อนวางบล็อกแรก เพื่อให้การเรียกที่ล้มเหลวไม่แก้ไข scene
    """
    blocks = server._parse_blocks_json(blocks_json)
    with server.store.lock:
        scene = server.store.get(scene_name or None)
        for _x, _y, _z, color in blocks:
            scene.resolve_color(color)
        for x, y, z, color in blocks:
            scene.place(x, y, z, color)
        server._sync_bridge(scene)
        return (
            "วาง "
            f"{len(blocks)}"
            " voxel ใน '"
            f"{scene.name}"
            "' — รวม "
            f"{scene.block_count()}"
            " บล็อก"
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
    เติ่มกล่อง 3D (เหมาะสร้างฐาน/ตัวบ้าน/กำแพง).

    Parameters
    ----------
    x1, x2, y1, y2, z1, z2 : int
        ขอบเขตแบบรวมปลายของแต่ละแกน ลำดับของคู่ไม่สำคัญ
    color : str, optional
        คีย์พาเลตหรือรหัส ``#RRGGBB`` ค่าเริ่มต้น ``"1"``
    scene_name : str, optional
        ชื่อ scene เป้าหมาย ค่าเริ่มต้นคือ scene ปัจจุบัน

    Returns
    -------
    str
        ข้อความยืนยันพร้อมจำนวน voxel ที่เติมและจำนวนบล็อกรวม

    Raises
    ------
    ValueError
        ถ้าปริมาตรเกิน ``MAX_TOOL_VOXELS`` หรือ ``color`` resolve ไม่ได้
    KeyError
        ถ้าไม่พบ scene เป้าหมาย

    Notes
    -----
    ขอบเขตถูกตรวจสอบก่อนเติม เพื่อให้การเรียกที่ล้มเหลวไม่แก้ไข scene
    """
    with server.store.lock:
        scene = server.store.get(scene_name or None)
        volume = (abs(x2 - x1) + 1) * (abs(y2 - y1) + 1) * (abs(z2 - z1) + 1)
        if volume > server.MAX_TOOL_VOXELS:
            msg = (
                f"fill_box supports at most {server.MAX_TOOL_VOXELS:,} voxels per call"
            )
            raise ValueError(msg)
        n = scene.fill_box(x1, x2, y1, y2, z1, z2, color)
        server._sync_bridge(scene)
        return f"เติม {n} voxel สี '{color}' — รวม {scene.block_count()} บล็อก"


@server.mcp.tool()
def voxelforge_remove_block(x: int, y: int, z: int, scene_name: str = "") -> str:
    """
    ลบ voxel ที่พิกัด.

    Parameters
    ----------
    x, y, z : int
        พิกัดกริดของ voxel
    scene_name : str, optional
        ชื่อ scene เป้าหมาย ค่าเริ่มต้นคือ scene ปัจจุบัน

    Returns
    -------
    str
        ``"ลบแล้ว"`` เมื่อลบสำเร็จ หรือ ``"ไม่มี voxel ตรงนั้น"`` เมื่อพิกัดว่าง

    Raises
    ------
    KeyError
        ถ้าไม่พบ scene เป้าหมาย

    Notes
    -----
    เมื่อพิกัดว่างจะไม่มีการประกาศ ``scene_update`` เพราะ scene ไม่เปลี่ยน
    """
    with server.store.lock:
        scene = server.store.get(scene_name or None)
        ok = scene.remove(x, y, z)
        if ok:
            server._sync_bridge(scene)
        return "ลบแล้ว" if ok else "ไม่มี voxel ตรงนั้น"


@server.mcp.tool()
def voxelforge_clear(scene_name: str = "") -> str:
    """
    ล้าง voxel ทั้งหมดในทุก layer.

    Parameters
    ----------
    scene_name : str, optional
        ชื่อ scene เป้าหมาย ค่าเริ่มต้นคือ scene ปัจจุบัน

    Returns
    -------
    str
        ข้อความยืนยันพร้อมชื่อ scene

    Raises
    ------
    KeyError
        ถ้าไม่พบ scene เป้าหมาย
    """
    with server.store.lock:
        scene = server.store.get(scene_name or None)
        scene.clear()
        server._sync_bridge(scene)
        return f"ล้าง scene '{scene.name}' แล้ว"
