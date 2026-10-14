"""Io MCP tools using the shared lock-owning server registry."""

from __future__ import annotations

import json
from pathlib import Path

from voxel_forge import server


@server.mcp.tool()
def voxelforge_save(scene_name: str = "") -> str:
    """บันทึก scene ลง ~/.voxel-forge/scenes/.

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
    with server.store.lock:
        scene = server.store.get(scene_name or None)
        path = server.save_scene(scene)
        return f"บันทึก '{scene.name}' ที่ {path}"


@server.mcp.tool()
def voxelforge_load(name: str) -> str:
    """โหลด scene จากไฟล์.

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
    scene = server.load_scene(name)
    with server.store.lock:
        server.store.register(scene)
        server._sync_bridge(scene)
        return f"โหลด '{name}' ({scene.block_count()} บล็อก)"


@server.mcp.tool()
def voxelforge_list_scenes() -> str:
    """รายชื่อ scene ใน session และไฟล์ที่เซฟ.

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
    with server.store.lock:
        active = server.store.list_active()
    return json.dumps(
        {"active_session": active, "saved_on_disk": server.list_saved_scenes()},
        ensure_ascii=False,
        indent=2,
    )


@server.mcp.tool()
def voxelforge_import_vox(file_path: str) -> str:
    """Import ไฟล์ .vox (MagicaVoxel / Goxel export format).

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
    scene = server.import_vox(file_path)
    with server.store.lock:
        server.store.register(scene)
        server._sync_bridge(scene)
        return (
            f"import '{file_path}' → scene '{scene.name}' ({scene.block_count()} voxel)"
        )


@server.mcp.tool()
def voxelforge_export_vox(scene_name: str = "", output_path: str = "") -> str:
    """Export เป็น .vox (เปิดใน Goxel / MagicaVoxel ได้).

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
    with server.store.lock:
        scene = server.store.get(scene_name or None)
        path = server._export_path(scene, output_path, ".vox")
        server.export_vox(scene, path)
        return f"export .vox → {path} ({scene.block_count()} voxel)"


@server.mcp.tool()
def voxelforge_export_obj(
    scene_name: str = "",
    output_path: str = "",
    merge_boxes: bool = True,  # ruff: ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]  # MCP schema
) -> str:
    """Export เป็น Wavefront .obj — merge_boxes=true รวม voxel ติดกัน (แนะนำ).

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
    with server.store.lock:
        scene = server.store.get(scene_name or None)
        suffix = "_merged.obj" if merge_boxes else ".obj"
        path = server._export_path(scene, output_path, suffix)
        server.export_obj(scene, path, merge_boxes=merge_boxes)
        stats = (
            server.merge_stats(scene)
            if merge_boxes
            else {"merged_boxes": scene.block_count()}
        )
        parts = stats["merged_boxes"] if merge_boxes else scene.block_count()
        return (
            "export .obj -> "
            f"{path}"
            " ("
            f"{parts}"
            " parts จาก "
            f"{scene.block_count()}"
            " voxels, merge="
            f"{merge_boxes}"
            ")"
        )


@server.mcp.tool()
def voxelforge_export_obj_legacy(scene_name: str = "", output_path: str = "") -> str:
    """Export เป็น Wavefront .obj (Goxel รองรับ).

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
    with server.store.lock:
        scene = server.store.get(scene_name or None)
        path = server._export_path(scene, output_path, ".obj")
        server.export_obj(scene, path, merge_boxes=False)
        return f"export .obj (no merge) -> {path} ({scene.block_count()} voxels)"


@server.mcp.tool()
def voxelforge_export_roblox_merged(scene_name: str = "", output_path: str = "") -> str:
    """Export Luau สำหรับ Roblox — รวม voxel เป็น Part ใหญ่ใน Model เดียว (ลดแลag).

    ใช้ Roblox_Studio MCP execute_luau (Edit mode) รันโค้ดที่ได้
    """
    with server.store.lock:
        scene = server.store.get(scene_name or None)
        stats = server.merge_stats(scene)
        if output_path:
            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(server.to_luau_merged(scene), encoding="utf-8")
        else:
            path = server.write_luau_file(scene)
        return (
            f"export Roblox merged -> {path}\n"
            f"  {stats['voxels']} voxels -> {stats['merged_boxes']} Parts "
            f"(ลด {stats['reduction_percent']}%)\n"
            f"  รันใน Studio ด้วย execute_luau"
        )
