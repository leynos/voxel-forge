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
    """อธิบาย VoxelForge และความสัมพันธ์กับ Goxel."""
    return (
        "VoxelForge — voxel editor ของเรา สร้างจากแนวค"
        "ิด Goxel (https://github.com/guillaumechereau"
        "/goxel)\nฟีเจอร์: 24-bit RGB, layers, unlimite"
        "d scene, export .vox (MagicaVoxel) และ .obj\nM"
        "CP ใช้ได้กับ Cursor, Claude Desktop, และ clie"
        "nt อื่นที่รองรับ Model Context Protocol\nGoxel"
        " ต้นฉบับเป็น GPL-3.0 — VoxelForge เป็น implem"
        "entation ใหม่ที่ออกแบบ MCP-first"
    )


@server.mcp.tool()
def voxelforge_create_scene(name: str) -> str:
    """สร้าง scene voxel ใหม่.

    Parameters
    ----------
    name : str
        ชื่อ scene ใช้เป็นชื่อไฟล์ได้ ต้องเป็นข้อความยาว 1-80 ตัวอักษร
        ห้ามมีตัวคั่นเส้นทางหรืออักขระควบคุม

    Returns
    -------
    str
        ข้อความยืนยันพร้อมชื่อ scene และ layer เริ่มต้น

    Raises
    ------
    ValueError
        ถ้าชื่อ scene ไม่ปลอดภัยสำหรับใช้เป็นชื่อไฟล์

    Notes
    -----
    Scene ใหม่ยังไม่ถูกบันทึกลงดิสก์ ใช้ ``voxelforge_save`` เมื่อต้องการบันทึก
    """
    with server.store.lock:
        scene = server.store.create(name)
        server._sync_bridge(scene)
        return f"สร้าง scene '{scene.name}' แล้ว (layer เริ่มต้น: {scene.layers[0].name})"


@server.mcp.tool()
def voxelforge_select_scene(name: str) -> str:
    """เลือก scene ที่กำลังแก้ไข.

    Parameters
    ----------
    name : str
        ชื่อ scene ที่โหลดไว้แล้วใน session นี้

    Returns
    -------
    str
        ข้อความยืนยันพร้อมจำนวนบล็อกของ scene

    Raises
    ------
    KeyError
        ถ้าไม่มี scene ชื่อนี้ใน session ให้ใช้ ``voxelforge_load`` โหลดจากดิสก์ก่อน
    """
    with server.store.lock:
        scene = server.store.select(name)
        server._sync_bridge(scene)
        return f"เลือก scene '{scene.name}' ({scene.block_count()} บล็อก)"


@server.mcp.tool()
def voxelforge_add_layer(name: str, scene_name: str = "") -> str:
    """เพิ่ม layer ใหม่ (เหมือน Goxel).

    Parameters
    ----------
    name : str
        ชื่อ layer ที่จะแสดงใน editor และ preview
    scene_name : str, optional
        ชื่อ scene เป้าหมาย ค่าเริ่มต้นคือ scene ปัจจุบัน

    Returns
    -------
    str
        ข้อความยืนยันพร้อมจำนวน layer ทั้งหมด

    Raises
    ------
    KeyError
        ถ้าไม่พบ scene เป้าหมาย
    """
    with server.store.lock:
        scene = server.store.get(scene_name or None)
        layer = scene.add_layer(name)
        server._sync_bridge(scene)
        return (
            "เพิ่ม layer '"
            f"{layer.name}"
            "' ใน '"
            f"{scene.name}"
            "' — รวม "
            f"{len(scene.layers)}"
            " layers"
        )


@server.mcp.tool()
def voxelforge_set_active_layer(index: int, scene_name: str = "") -> str:
    """ตั้ง layer ที่ใช้งาน (index เริ่ม 0).

    Parameters
    ----------
    index : int
        ดัชนี layer เริ่มนับจาก 0
    scene_name : str, optional
        ชื่อ scene เป้าหมาย ค่าเริ่มต้นคือ scene ปัจจุบัน

    Returns
    -------
    str
        ข้อความยืนยันพร้อมชื่อ layer ที่เลือก

    Raises
    ------
    ValueError
        ถ้า ``index`` อยู่นอกช่วงของ layer ที่มีอยู่
    KeyError
        ถ้าไม่พบ scene เป้าหมาย
    """
    with server.store.lock:
        scene = server.store.get(scene_name or None)
        if index < 0 or index >= len(scene.layers):
            msg = f"layer index ต้องอยู่ระหว่าง 0..{len(scene.layers) - 1}"
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
    """กำหนดสีในพาเลต (24-bit RGB).

    Parameters
    ----------
    color_key : str
        คีย์ของสีที่จะกำหนดหรือเขียนทับ
    r, g, b : int
        ค่าแต่ละช่องเป็นจำนวนเต็ม 0-255 (ไม่รับ float หรือสตริงตัวเลข)
    scene_name : str, optional
        ชื่อ scene เป้าหมาย ค่าเริ่มต้นคือ scene ปัจจุบัน

    Returns
    -------
    str
        ข้อความยืนยันพร้อมค่าสีที่ตั้ง

    Raises
    ------
    ValueError
        ถ้าค่าใดไม่ใช่จำนวนเต็มในช่วง 0-255
    KeyError
        ถ้าไม่พบ scene เป้าหมาย
    """
    with server._edit_scene(scene_name) as scene:
        scene.set_palette_color(color_key, r, g, b)
        return f"พาเลต {color_key} = RGB({r},{g},{b})"


@server.mcp.tool()
def voxelforge_preview(scene_name: str = "") -> str:
    """แสดงสรุป + มุมมอง ASCII แต่ละชั้น Y (ให้ AI ตรวจรูปทรง).

    Parameters
    ----------
    scene_name : str, optional
        ชื่อ scene เป้าหมาย ค่าเริ่มต้นคือ scene ปัจจุบัน

    Returns
    -------
    str
        ข้อความสรุปและภาพ ASCII ของ scene

    Raises
    ------
    KeyError
        ถ้าไม่พบ scene เป้าหมาย
    """
    with server.store.lock:
        scene = server.store.get(scene_name or None)
        return server.summary(scene)


@server.mcp.tool()
def voxelforge_get_info(scene_name: str = "") -> str:
    """ข้อมูล scene เป็น JSON.

    Parameters
    ----------
    scene_name : str, optional
        ชื่อ scene เป้าหมาย ค่าเริ่มต้นคือ scene ปัจจุบัน

    Returns
    -------
    str
        JSON ของ ``VoxelScene.to_dict()`` (ชื่อ, voxel_size, พาเลต, layers)

    Raises
    ------
    KeyError
        ถ้าไม่พบ scene เป้าหมาย

    Notes
    -----
    เป็นการอ่านเท่านั้น ไม่แก้ไข scene และไม่ประกาศ ``scene_update``
    """
    with server.store.lock:
        scene = server.store.get(scene_name or None)
        return json.dumps(scene.to_dict(), ensure_ascii=False, indent=2)


@server.mcp.tool()
def voxelforge_merge_stats(scene_name: str = "") -> str:
    """ดูว่ารวม voxel เป็นกล่องแล้วลด part/mesh ได้เท่าไร (ก่อน export).

    Parameters
    ----------
    scene_name : str, optional
        ชื่อ scene เป้าหมาย ค่าเริ่มต้นคือ scene ปัจจุบัน

    Returns
    -------
    str
        จำนวน voxel, จำนวนกล่องหลังรวม, และเปอร์เซ็นต์ที่ลดได้

    Raises
    ------
    KeyError
        ถ้าไม่พบ scene เป้าหมาย
    """
    with server.store.lock:
        scene = server.store.get(scene_name or None)
        stats = server.merge_stats(scene)
        return (
            f"Scene '{scene.name}':\n"
            f"  voxels (หลัง dedupe ทับกัน): {stats['voxels']}\n"
            f"  merged boxes (parts): {stats['merged_boxes']}\n"
            f"  ลดได้: {stats['parts_saved']} ({stats['reduction_percent']}%)"
        )


@server.mcp.tool()
def voxelforge_set_voxel_size(size: float, scene_name: str = "") -> str:
    """ตั้งขนาด voxel ใน world (1.0=ปกติ, 0.25=ละเอียด 4 เท่า).

    Parameters
    ----------
    size : float
        ขนาดต่อหนึ่งช่องกริด ค่าถูกจำกัดไว้ในช่วง 0.05-2.0
    scene_name : str, optional
        ชื่อ scene เป้าหมาย ค่าเริ่มต้นคือ scene ปัจจุบัน

    Returns
    -------
    str
        ข้อความยืนยันพร้อมค่า voxel_size ที่ใช้จริง

    Raises
    ------
    KeyError
        ถ้าไม่พบ scene เป้าหมาย
    """
    with server.store.lock:
        scene = server.store.get(scene_name or None)
        scene.voxel_size = max(0.05, min(2.0, float(size)))
        server._sync_bridge(scene)
        return f"ตั้ง voxel_size={scene.voxel_size} ใน '{scene.name}'"


@server.mcp.tool()
def voxelforge_default_palette() -> str:
    """พาเลตสีเริ่มต้น.

    Returns
    -------
    str
        JSON ของพาเลตเริ่มต้น (คีย์ → [r, g, b])
    """
    return json.dumps({k: list(v) for k, v in server.DEFAULT_PALETTE.items()}, indent=2)
