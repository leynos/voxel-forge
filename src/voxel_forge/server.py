"""MCP Server — VoxelForge (Goxel-inspired) for Cursor, Claude, and other AI clients."""

from __future__ import annotations

import json
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from . import bridge as bridge_module
from .bridge import BRIDGE_HTTP_PORT, notify_scene_update, start_bridge_background
from .export_roblox import to_luau_merged, write_luau_file
from .mesh_merge import merge_stats
from .model import DEFAULT_PALETTE, SceneStore, VoxelScene
from .preview import summary
from .procedural import build_chibi_bear, build_tree
from .scene_store import list_saved_scenes, load_scene, save_scene
from .vox_io import export_obj, export_vox, import_vox

mcp = FastMCP(
    "VoxelForge",
    instructions=(
        "VoxelForge — โปรแกรมสร้าง voxel 3D แบบ Goxel (24-bit RGB, layers, export .vox/.obj).\n"
        "ขั้นตอน: voxelforge_create_scene → voxelforge_place_many / voxelforge_fill_box → "
        "voxelforge_preview → voxelforge_export_vox หรือ voxelforge_export_obj\n"
        "เปิด editor 3D: voxelforge_launch_editor\n"
        "รองรับ import ไฟล์ MagicaVoxel (.vox) ที่ Goxel ใช้ได้"
    ),
)

store = SceneStore()
MAX_TOOL_VOXELS: int = 100_000
# Bounds the raw request before json.loads materialises it. At the limit above a
# well-formed payload is about 2.5 million characters, so this leaves room for
# formatting while still refusing a payload that could exhaust memory.
MAX_BLOCKS_JSON_CHARS: int = 8_000_000


def _ensure_bridge() -> None:
    """Start the bridge if needed and hand it this module's scene registry."""
    start_bridge_background()
    bridge_module.use_store(store)


def _sync_bridge(scene: VoxelScene) -> None:
    """Broadcast one scene update; callers hold the registry lock for the mutation."""
    _ensure_bridge()
    notify_scene_update(scene)


def _parse_blocks_json(blocks_json: str) -> list[tuple[int, int, int, str]]:
    """
    Parse a bulk voxel JSON array, rejecting oversized text before decoding.

    Raises ``ValueError`` — including ``json.JSONDecodeError`` — when the text
    exceeds ``MAX_BLOCKS_JSON_CHARS``, is not a JSON array, holds more than
    ``MAX_TOOL_VOXELS`` rows, or carries a row shorter than four entries.
    """
    if not isinstance(blocks_json, str):
        raise ValueError("blocks ต้องเป็น JSON string")
    if len(blocks_json) > MAX_BLOCKS_JSON_CHARS:
        raise ValueError(f"blocks payload must be at most {MAX_BLOCKS_JSON_CHARS:,} characters")
    data = json.loads(blocks_json)
    if not isinstance(data, list):
        raise ValueError("blocks ต้องเป็น JSON array")
    if len(data) > MAX_TOOL_VOXELS:
        raise ValueError(f"place_many supports at most {MAX_TOOL_VOXELS:,} voxels per call")
    out: list[tuple[int, int, int, str]] = []
    for row in data:
        if not isinstance(row, (list, tuple)) or len(row) < 4:
            raise ValueError(f"รูปแบบบล็อกไม่ถูก: {row}")
        out.append((int(row[0]), int(row[1]), int(row[2]), str(row[3])))
    return out


def _exports_dir() -> Path:
    """Return the export directory, creating it when absent."""
    root = Path.home() / ".voxel-forge" / "exports"
    root.mkdir(parents=True, exist_ok=True)
    return root


@mcp.tool()
def voxelforge_about() -> str:
    """อธิบาย VoxelForge และความสัมพันธ์กับ Goxel."""
    return (
        "VoxelForge — voxel editor ของเรา สร้างจากแนวคิด Goxel (https://github.com/guillaumechereau/goxel)\n"
        "ฟีเจอร์: 24-bit RGB, layers, unlimited scene, export .vox (MagicaVoxel) และ .obj\n"
        "MCP ใช้ได้กับ Cursor, Claude Desktop, และ client อื่นที่รองรับ Model Context Protocol\n"
        "Goxel ต้นฉบับเป็น GPL-3.0 — VoxelForge เป็น implementation ใหม่ที่ออกแบบ MCP-first"
    )


@mcp.tool()
def voxelforge_create_scene(name: str) -> str:
    """
    สร้าง scene voxel ใหม่.

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
    with store.lock:
        scene = store.create(name)
        _sync_bridge(scene)
        return f"สร้าง scene '{scene.name}' แล้ว (layer เริ่มต้น: {scene.layers[0].name})"


@mcp.tool()
def voxelforge_select_scene(name: str) -> str:
    """
    เลือก scene ที่กำลังแก้ไข.

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
    with store.lock:
        scene = store.select(name)
        _sync_bridge(scene)
        return f"เลือก scene '{scene.name}' ({scene.block_count()} บล็อก)"


@mcp.tool()
def voxelforge_add_layer(name: str, scene_name: str = "") -> str:
    """
    เพิ่ม layer ใหม่ (เหมือน Goxel).

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
    with store.lock:
        scene = store.get(scene_name or None)
        layer = scene.add_layer(name)
        _sync_bridge(scene)
        return f"เพิ่ม layer '{layer.name}' ใน '{scene.name}' — รวม {len(scene.layers)} layers"


@mcp.tool()
def voxelforge_set_active_layer(index: int, scene_name: str = "") -> str:
    """
    ตั้ง layer ที่ใช้งาน (index เริ่ม 0).

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
    with store.lock:
        scene = store.get(scene_name or None)
        if index < 0 or index >= len(scene.layers):
            raise ValueError(f"layer index ต้องอยู่ระหว่าง 0..{len(scene.layers) - 1}")
        scene.active_layer = index
        _sync_bridge(scene)
        return f"active layer = {scene.layers[index].name}"


@mcp.tool()
def voxelforge_set_palette(
    color_key: str,
    r: int,
    g: int,
    b: int,
    scene_name: str = "",
) -> str:
    """
    กำหนดสีในพาเลต (24-bit RGB).

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
    with store.lock:
        scene = store.get(scene_name or None)
        scene.set_palette_color(color_key, r, g, b)
        _sync_bridge(scene)
        return f"พาเลต {color_key} = RGB({r},{g},{b})"


@mcp.tool()
def voxelforge_place_block(
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
    with store.lock:
        scene = store.get(scene_name or None)
        scene.place(x, y, z, color)
        _sync_bridge(scene)
        return f"วาง ({x},{y},{z}) สี '{color}' — รวม {scene.block_count()} บล็อก"


@mcp.tool()
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
    blocks = _parse_blocks_json(blocks_json)
    with store.lock:
        scene = store.get(scene_name or None)
        for _x, _y, _z, color in blocks:
            scene.resolve_color(color)
        for x, y, z, color in blocks:
            scene.place(x, y, z, color)
        _sync_bridge(scene)
        return f"วาง {len(blocks)} voxel ใน '{scene.name}' — รวม {scene.block_count()} บล็อก"


@mcp.tool()
def voxelforge_fill_box(
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
    with store.lock:
        scene = store.get(scene_name or None)
        volume = (abs(x2 - x1) + 1) * (abs(y2 - y1) + 1) * (abs(z2 - z1) + 1)
        if volume > MAX_TOOL_VOXELS:
            raise ValueError(f"fill_box supports at most {MAX_TOOL_VOXELS:,} voxels per call")
        n = scene.fill_box(x1, x2, y1, y2, z1, z2, color)
        _sync_bridge(scene)
        return f"เติม {n} voxel สี '{color}' — รวม {scene.block_count()} บล็อก"


@mcp.tool()
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
    with store.lock:
        scene = store.get(scene_name or None)
        ok = scene.remove(x, y, z)
        if ok:
            _sync_bridge(scene)
        return "ลบแล้ว" if ok else "ไม่มี voxel ตรงนั้น"


@mcp.tool()
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
    with store.lock:
        scene = store.get(scene_name or None)
        scene.clear()
        _sync_bridge(scene)
        return f"ล้าง scene '{scene.name}' แล้ว"


@mcp.tool()
def voxelforge_preview(scene_name: str = "") -> str:
    """
    แสดงสรุป + มุมมอง ASCII แต่ละชั้น Y (ให้ AI ตรวจรูปทรง).

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
    with store.lock:
        scene = store.get(scene_name or None)
        return summary(scene)


@mcp.tool()
def voxelforge_get_info(scene_name: str = "") -> str:
    """
    ข้อมูล scene เป็น JSON.

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
    with store.lock:
        scene = store.get(scene_name or None)
        return json.dumps(scene.to_dict(), ensure_ascii=False, indent=2)


@mcp.tool()
def voxelforge_save(scene_name: str = "") -> str:
    """
    บันทึก scene ลง ~/.voxel-forge/scenes/.

    Parameters
    ----------
    scene_name : str, optional
        ชื่อ scene เป้าหมาย ค่าเริ่มต้นคือ scene ปัจจุบัน

    Returns
    -------
    str
        ข้อความยืนยันพร้อมเส้นทางไฟล์ที่บันทึก

    Raises
    ------
    KeyError
        ถ้าไม่พบ scene เป้าหมาย
    ValueError
        ถ้าชื่อ scene ไม่ปลอดภัยสำหรับใช้เป็นชื่อไฟล์
    OSError
        ถ้าเขียนโฟลเดอร์หรือไฟล์ไม่สำเร็จ
    """
    with store.lock:
        scene = store.get(scene_name or None)
        path = save_scene(scene)
        return f"บันทึก '{scene.name}' ที่ {path}"


@mcp.tool()
def voxelforge_load(name: str) -> str:
    """
    โหลด scene จากไฟล์.

    Parameters
    ----------
    name : str
        ชื่อ scene ที่บันทึกไว้ ไม่ต้องใส่ ``.json``

    Returns
    -------
    str
        ข้อความยืนยันพร้อมจำนวนบล็อก

    Raises
    ------
    FileNotFoundError
        ถ้าไม่พบไฟล์ scene ชื่อนี้
    ValueError
        ถ้าชื่อไม่ปลอดภัย หรือเนื้อหาไฟล์ไม่ผ่านการตรวจสอบ
    OSError
        ถ้าอ่านไฟล์ไม่สำเร็จ
    """
    scene = load_scene(name)
    with store.lock:
        store.register(scene)
        _sync_bridge(scene)
        return f"โหลด '{name}' ({scene.block_count()} บล็อก)"


@mcp.tool()
def voxelforge_list_scenes() -> str:
    """
    รายชื่อ scene ใน session และไฟล์ที่เซฟ.

    Returns
    -------
    str
        JSON ที่มี ``active_session`` (scene ในหน่วยความจำ) และ ``saved_on_disk``
        (ไฟล์ใน ``~/.voxel-forge/scenes``)

    Raises
    ------
    OSError
        ถ้าเข้าถึงโฟลเดอร์ scene ไม่สำเร็จ การอ่านล้มเหลวจะไม่ถูกกลืนเป็นรายการว่าง
    """
    with store.lock:
        active = store.list_active()
    return json.dumps(
        {"active_session": active, "saved_on_disk": list_saved_scenes()},
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool()
def voxelforge_import_vox(file_path: str) -> str:
    """
    Import ไฟล์ .vox (MagicaVoxel / Goxel export format).

    Parameters
    ----------
    file_path : str
        เส้นทางไฟล์ ``.vox``

    Returns
    -------
    str
        ข้อความยืนยันพร้อมชื่อ scene ที่ได้และจำนวน voxel

    Raises
    ------
    ValueError
        ถ้าไฟล์ไม่ใช่รูปแบบ ``.vox`` ที่ถูกต้อง
    OSError
        ถ้าอ่านไฟล์ไม่สำเร็จ
    """
    scene = import_vox(file_path)
    with store.lock:
        store.register(scene)
        _sync_bridge(scene)
        return f"import '{file_path}' → scene '{scene.name}' ({scene.block_count()} voxel)"


@mcp.tool()
def voxelforge_export_vox(scene_name: str = "", output_path: str = "") -> str:
    """
    Export เป็น .vox (เปิดใน Goxel / MagicaVoxel ได้).

    Parameters
    ----------
    scene_name : str, optional
        ชื่อ scene เป้าหมาย ค่าเริ่มต้นคือ scene ปัจจุบัน
    output_path : str, optional
        เส้นทางไฟล์ปลายทาง ค่าเริ่มต้นคือ ``~/.voxel-forge/exports/<name>.vox``

    Returns
    -------
    str
        ข้อความยืนยันพร้อมเส้นทางไฟล์และจำนวน voxel

    Raises
    ------
    ValueError
        ถ้า scene ใหญ่เกิน 256 ช่องต่อแกน มีสีเกิน 255 สี หรือมี voxel ทับกัน
        ระหว่าง layer ที่มองเห็นได้
    KeyError
        ถ้าไม่พบ scene เป้าหมาย
    OSError
        ถ้าเขียนไฟล์ไม่สำเร็จ
    """
    with store.lock:
        scene = store.get(scene_name or None)
        if output_path:
            path = Path(output_path)
        else:
            path = _exports_dir() / f"{scene.name}.vox"
        export_vox(scene, path)
        return f"export .vox → {path} ({scene.block_count()} voxel)"


@mcp.tool()
def voxelforge_merge_stats(scene_name: str = "") -> str:
    """
    ดูว่ารวม voxel เป็นกล่องแล้วลด part/mesh ได้เท่าไร (ก่อน export).

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
    with store.lock:
        scene = store.get(scene_name or None)
        stats = merge_stats(scene)
        return (
            f"Scene '{scene.name}':\n"
            f"  voxels (หลัง dedupe ทับกัน): {stats['voxels']}\n"
            f"  merged boxes (parts): {stats['merged_boxes']}\n"
            f"  ลดได้: {stats['parts_saved']} ({stats['reduction_percent']}%)"
        )


@mcp.tool()
def voxelforge_export_obj(
    scene_name: str = "",
    output_path: str = "",
    merge_boxes: bool = True,
) -> str:
    """
    Export เป็น Wavefront .obj — merge_boxes=true รวม voxel ติดกัน (แนะนำ).

    Parameters
    ----------
    scene_name : str, optional
        ชื่อ scene เป้าหมาย ค่าเริ่มต้นคือ scene ปัจจุบัน
    output_path : str, optional
        เส้นทางไฟล์ปลายทาง ค่าเริ่มต้นคือ ``~/.voxel-forge/exports/``
    merge_boxes : bool, optional
        รวม voxel ที่ติดกันเป็นกล่องใหญ่ ค่าเริ่มต้น ``True``

    Returns
    -------
    str
        ข้อความยืนยันพร้อมเส้นทาง จำนวน part และจำนวน voxel

    Raises
    ------
    KeyError
        ถ้าไม่พบ scene เป้าหมาย
    OSError
        ถ้าเขียนไฟล์ไม่สำเร็จ
    """
    with store.lock:
        scene = store.get(scene_name or None)
        if output_path:
            path = Path(output_path)
        else:
            suffix = "_merged" if merge_boxes else ""
            path = _exports_dir() / f"{scene.name}{suffix}.obj"
        export_obj(scene, path, merge_boxes=merge_boxes)
        stats = merge_stats(scene) if merge_boxes else {"merged_boxes": scene.block_count()}
        parts = stats["merged_boxes"] if merge_boxes else scene.block_count()
        return f"export .obj -> {path} ({parts} parts จาก {scene.block_count()} voxels, merge={merge_boxes})"


@mcp.tool()
def voxelforge_export_roblox_merged(scene_name: str = "", output_path: str = "") -> str:
    """
    Export Luau สำหรับ Roblox — รวม voxel เป็น Part ใหญ่ใน Model เดียว (ลดแลag).
    ใช้ Roblox_Studio MCP execute_luau (Edit mode) รันโค้ดที่ได้
    """
    with store.lock:
        scene = store.get(scene_name or None)
        stats = merge_stats(scene)
        if output_path:
            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(to_luau_merged(scene), encoding="utf-8")
        else:
            path = write_luau_file(scene)
        return (
            f"export Roblox merged -> {path}\n"
            f"  {stats['voxels']} voxels -> {stats['merged_boxes']} Parts "
            f"(ลด {stats['reduction_percent']}%)\n"
            f"  รันใน Studio ด้วย execute_luau"
        )


@mcp.tool()
def voxelforge_export_obj_legacy(scene_name: str = "", output_path: str = "") -> str:
    """
    Export เป็น Wavefront .obj (Goxel รองรับ).

    Parameters
    ----------
    scene_name : str, optional
        ชื่อ scene เป้าหมาย ค่าเริ่มต้นคือ scene ปัจจุบัน
    output_path : str, optional
        เส้นทางไฟล์ปลายทาง ค่าเริ่มต้นคือ ``~/.voxel-forge/exports/``

    Returns
    -------
    str
        ข้อความยืนยันพร้อมเส้นทางและจำนวน voxel

    Raises
    ------
    KeyError
        ถ้าไม่พบ scene เป้าหมาย
    OSError
        ถ้าเขียนไฟล์ไม่สำเร็จ
    """
    with store.lock:
        scene = store.get(scene_name or None)
        if output_path:
            path = Path(output_path)
        else:
            path = _exports_dir() / f"{scene.name}.obj"
        export_obj(scene, path, merge_boxes=False)
        return f"export .obj (no merge) -> {path} ({scene.block_count()} voxels)"


@mcp.tool()
def voxelforge_build_chibi_bear(name: str = "chibi_bear", resolution: int = 3) -> str:
    """
    สร้างรูปปั้นหมี chibi (resolution 2-4 แนะนำ).

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
    scene = build_chibi_bear(name=name, resolution=resolution)
    with store.lock:
        store.register(scene)
        _sync_bridge(scene)
        return f"สร้างหมี chibi '{scene.name}' — {scene.block_count()} voxels (resolution {resolution})"


@mcp.tool()
def voxelforge_build_tree(name: str = "tree", resolution: int = 4) -> str:
    """
    สร้างต้นไม้ procedural ความละเอียดปรับได้.
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
    scene = build_tree(name=name, resolution=resolution)
    with store.lock:
        store.register(scene)
        _sync_bridge(scene)
        vs = scene.voxel_size
        return (
            f"สร้างต้นไม้ '{scene.name}' — {scene.block_count()} voxels, "
            f"voxel_size={vs} (resolution {resolution}x)\n"
            f"เปิด editor เพื่อดู 3D หรือ voxelforge_preview ตรวจ ASCII"
        )


@mcp.tool()
def voxelforge_set_voxel_size(size: float, scene_name: str = "") -> str:
    """
    ตั้งขนาด voxel ใน world (1.0=ปกติ, 0.25=ละเอียด 4 เท่า).

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
    with store.lock:
        scene = store.get(scene_name or None)
        scene.voxel_size = max(0.05, min(2.0, float(size)))
        _sync_bridge(scene)
        return f"ตั้ง voxel_size={scene.voxel_size} ใน '{scene.name}'"


@mcp.tool()
def voxelforge_default_palette() -> str:
    """
    พาเลตสีเริ่มต้น.

    Returns
    -------
    str
        JSON ของพาเลตเริ่มต้น (คีย์ → [r, g, b])
    """
    return json.dumps({k: list(v) for k, v in DEFAULT_PALETTE.items()}, indent=2)


@mcp.tool()
def voxelforge_launch_editor() -> str:
    """
    เปิด VoxelForge Web Editor ในเบราว์เซอร์ (Three.js 3D view).
    Bridge sync อัตโนมัติผ่าน WebSocket — แก้ใน editor หรือผ่าน MCP ได้ทั้งคู่
    """
    _ensure_bridge()
    editor_dir = Path(__file__).resolve().parents[2] / "editor"
    index = editor_dir / "index.html"
    if not index.exists():
        return (
            f"Bridge ทำงานที่ ws://127.0.0.1:8765 และ http://127.0.0.1:{BRIDGE_HTTP_PORT}\n"
            "รัน editor: cd editor && npm install && npm run dev\n"
            "แล้วเปิด http://localhost:5173"
        )

    import webbrowser

    webbrowser.open("http://localhost:5173")
    return (
        "เปิด http://localhost:5173 แล้ว (ถ้ายังไม่รัน editor ให้รัน `cd editor && npm run dev` ก่อน)\n"
        f"Bridge: ws://127.0.0.1:8765 | HTTP scene: http://127.0.0.1:{BRIDGE_HTTP_PORT}/scene"
    )


def main() -> None:
    """Run the MCP server on stdio, or print usage and exit for ``--help``.

    Argument parsing happens before the bridge starts so that ``--help``
    answers and exits without binding a socket. ``argparse`` raises
    ``SystemExit`` for ``--help``, which is why the server is only reached once
    parsing returns.
    """
    import argparse

    parser = argparse.ArgumentParser(
        prog="voxel-forge-mcp",
        description="VoxelForge MCP server (stdio transport) with an editor bridge.",
    )
    parser.parse_args()
    _ensure_bridge()
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
