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
    """อธิบาย VoxelForge และความสัมพันธ์กับ Goxel."""
    return (
        "VoxelForge — voxel editor ของเรา สร้างจากแนวคิด Goxel (https://github.com/guillaumechereau/goxel)\n"
        "ฟีเจอร์: 24-bit RGB, layers, unlimited scene, "
        "export .vox (MagicaVoxel) และ .obj\n"
        "MCP ใช้ได้กับ Cursor, Claude Desktop, "
        "และ client อื่นที่รองรับ Model Context Protocol\n"
        "Goxel ต้นฉบับเป็น GPL-3.0 — VoxelForge เป็น implementation ใหม่ที่ออกแบบ MCP-first"
    )


@server.mcp.tool()
def voxelforge_create_scene(name: str) -> str:
    """สร้าง scene voxel ใหม่."""
    scene = server.store.create(name)
    server._sync_bridge(scene)
    return f"สร้าง scene '{scene.name}' แล้ว (layer เริ่มต้น: {scene.layers[0].name})"


@server.mcp.tool()
def voxelforge_select_scene(name: str) -> str:
    """เลือก scene ที่กำลังแก้ไข."""
    scene = server.store.set_current(name)
    server._sync_bridge(scene)
    return f"เลือก scene '{scene.name}' ({scene.block_count()} บล็อก)"


@server.mcp.tool()
def voxelforge_add_layer(name: str, scene_name: str = "") -> str:
    """เพิ่ม layer ใหม่ (เหมือน Goxel)."""
    scene = server.store.get(scene_name or None)
    layer = scene.add_layer(name)
    server._sync_bridge(scene)
    return (
        f"เพิ่ม layer '{layer.name}' ใน '{scene.name}' — รวม {len(scene.layers)} layers"
    )


@server.mcp.tool()
def voxelforge_set_active_layer(index: int, scene_name: str = "") -> str:
    """ตั้ง layer ที่ใช้งาน (index เริ่ม 0)."""
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
    """กำหนดสีในพาเลต (24-bit RGB)."""
    scene = server.store.get(scene_name or None)
    scene.set_palette_color(color_key, r, g, b)
    server._sync_bridge(scene)
    return f"พาเลต {color_key} = RGB({r},{g},{b})"


@server.mcp.tool()
# pylint: disable-next=too-many-arguments,too-many-positional-arguments  # MCP schema
def voxelforge_place_block(  # ruff: ignore[too-many-arguments, too-many-positional-arguments]  # MCP tool schema
    x: int,
    y: int,
    z: int,
    color: str = "1",
    scene_name: str = "",
) -> str:
    """วาง voxel 1 ลูกที่พิกัด (x,y,z)."""
    scene = server.store.get(scene_name or None)
    scene.place(x, y, z, color)
    server._sync_bridge(scene)
    return f"วาง ({x},{y},{z}) สี '{color}' — รวม {scene.block_count()} บล็อก"


@server.mcp.tool()
def voxelforge_place_many(blocks_json: str, scene_name: str = "") -> str:
    """
    วางหลาย voxel จาก JSON array.

    รูปแบบ: [[x,y,z,"1"], [1,0,0,"2"], ...] หรือใช้ #RRGGBB เป็นสี.
    """
    scene = server.store.get(scene_name or None)
    blocks = server._parse_blocks_json(blocks_json)
    for _x, _y, _z, color in blocks:
        scene.resolve_color(color)
    for x, y, z, color in blocks:
        scene.place(x, y, z, color)
    server._sync_bridge(scene)
    return f"วาง {len(blocks)} voxel ใน '{scene.name}' — รวม {scene.block_count()} บล็อก"


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
    """เติ่มกล่อง 3D (เหมาะสร้างฐาน/ตัวบ้าน/กำแพง)."""
    scene = server.store.get(scene_name or None)
    volume = (abs(x2 - x1) + 1) * (abs(y2 - y1) + 1) * (abs(z2 - z1) + 1)
    if volume > server.MAX_TOOL_VOXELS:
        msg = f"fill_box supports at most {server.MAX_TOOL_VOXELS:,} voxels per call"
        raise ValueError(msg)
    n = scene.fill_box(x1, x2, y1, y2, z1, z2, color)
    server._sync_bridge(scene)
    return f"เติม {n} voxel สี '{color}' — รวม {scene.block_count()} บล็อก"


@server.mcp.tool()
def voxelforge_remove_block(x: int, y: int, z: int, scene_name: str = "") -> str:
    """ลบ voxel ที่พิกัด."""
    scene = server.store.get(scene_name or None)
    ok = scene.remove(x, y, z)
    if ok:
        server._sync_bridge(scene)
    return "ลบแล้ว" if ok else "ไม่มี voxel ตรงนั้น"


@server.mcp.tool()
def voxelforge_clear(scene_name: str = "") -> str:
    """ล้าง voxel ทั้งหมด."""
    scene = server.store.get(scene_name or None)
    scene.clear()
    server._sync_bridge(scene)
    return f"ล้าง scene '{scene.name}' แล้ว"


@server.mcp.tool()
def voxelforge_preview(scene_name: str = "") -> str:
    """แสดงสรุป + มุมมอง ASCII แต่ละชั้น Y (ให้ AI ตรวจรูปทรง)."""
    scene = server.store.get(scene_name or None)
    return summary(scene)


@server.mcp.tool()
def voxelforge_get_info(scene_name: str = "") -> str:
    """ข้อมูล scene เป็น JSON."""
    scene = server.store.get(scene_name or None)
    return json.dumps(scene.to_dict(), ensure_ascii=False, indent=2)


@server.mcp.tool()
def voxelforge_save(scene_name: str = "") -> str:
    """บันทึก scene ลง ~/.voxel-forge/scenes/."""
    scene = server.store.get(scene_name or None)
    path = scene.save()
    return f"บันทึก '{scene.name}' ที่ {path}"


@server.mcp.tool()
def voxelforge_load(name: str) -> str:
    """โหลด scene จากไฟล์."""
    scene = VoxelScene.load(name)
    server.store._scenes[name] = scene
    server.store._current = name
    server._sync_bridge(scene)
    return f"โหลด '{name}' ({scene.block_count()} บล็อก)"


@server.mcp.tool()
def voxelforge_list_scenes() -> str:
    """รายชื่อ scene ใน session และไฟล์ที่เซฟ."""
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
    """ตั้งขนาด voxel ใน world (1.0=ปกติ, 0.25=ละเอียด 4 เท่า)."""
    scene = server.store.get(scene_name or None)
    scene.voxel_size = max(0.05, min(2.0, float(size)))
    server._sync_bridge(scene)
    return f"ตั้ง voxel_size={scene.voxel_size} ใน '{scene.name}'"


@server.mcp.tool()
def voxelforge_default_palette() -> str:
    """พาเลตสีเริ่มต้น."""
    return json.dumps({k: list(v) for k, v in DEFAULT_PALETTE.items()}, indent=2)
