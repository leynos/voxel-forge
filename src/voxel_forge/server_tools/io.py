"""Import, export and editor-launch MCP tools.

Mutable server state is reached through the :mod:`voxel_forge.server` module
object rather than by importing its attributes, so tests that replace
``server.store`` or ``server._sync_bridge`` observe the substitution.
"""

from pathlib import Path

from voxel_forge import server
from voxel_forge.bridge import BRIDGE_HTTP_PORT
from voxel_forge.export_roblox import to_luau_merged, write_luau_file
from voxel_forge.mesh_merge import merge_stats
from voxel_forge.vox_io import export_obj, export_vox, import_vox


@server.mcp.tool()
def voxelforge_import_vox(file_path: str) -> str:
    """Import ไฟล์ .vox (MagicaVoxel / Goxel export format)."""
    scene = import_vox(file_path)
    server.store._scenes[scene.name] = scene
    server.store._current = scene.name
    server._sync_bridge(scene)
    return f"import '{file_path}' → scene '{scene.name}' ({scene.block_count()} voxel)"


@server.mcp.tool()
def voxelforge_export_vox(scene_name: str = "", output_path: str = "") -> str:
    """Export เป็น .vox (เปิดใน Goxel / MagicaVoxel ได้)."""
    scene = server.store.get(scene_name or None)
    path = (
        Path(output_path)
        if output_path
        else server._exports_dir() / f"{scene.name}.vox"
    )
    export_vox(scene, path)
    return f"export .vox → {path} ({scene.block_count()} voxel)"


@server.mcp.tool()
def voxelforge_merge_stats(scene_name: str = "") -> str:
    """ดูว่ารวม voxel เป็นกล่องแล้วลด part/mesh ได้เท่าไร (ก่อน export)."""
    scene = server.store.get(scene_name or None)
    stats = merge_stats(scene)
    return (
        f"Scene '{scene.name}':\n"
        f"  voxels (หลัง dedupe ทับกัน): {stats['voxels']}\n"
        f"  merged boxes (parts): {stats['merged_boxes']}\n"
        f"  ลดได้: {stats['parts_saved']} ({stats['reduction_percent']}%)"
    )


@server.mcp.tool()
def voxelforge_export_obj(
    scene_name: str = "",
    output_path: str = "",
    merge_boxes: bool = True,  # ruff: ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]  # published MCP tool schema
) -> str:
    """Export เป็น Wavefront .obj — merge_boxes=true รวม voxel ติดกัน (แนะนำ)."""
    scene = server.store.get(scene_name or None)
    if output_path:
        path = Path(output_path)
    else:
        suffix = "_merged" if merge_boxes else ""
        path = server._exports_dir() / f"{scene.name}{suffix}.obj"
    export_obj(scene, path, merge_boxes=merge_boxes)
    stats = merge_stats(scene) if merge_boxes else {"merged_boxes": scene.block_count()}
    parts = stats["merged_boxes"] if merge_boxes else scene.block_count()
    return (
        f"export .obj -> {path} ({parts} parts จาก "
        f"{scene.block_count()} voxels, merge={merge_boxes})"
    )


@server.mcp.tool()
def voxelforge_export_roblox_merged(scene_name: str = "", output_path: str = "") -> str:
    """
    Export Luau สำหรับ Roblox — รวม voxel เป็น Part ใหญ่ใน Model เดียว (ลดแลag).

    ใช้ Roblox_Studio MCP execute_luau (Edit mode) รันโค้ดที่ได้.
    """
    scene = server.store.get(scene_name or None)
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


@server.mcp.tool()
def voxelforge_export_obj_legacy(scene_name: str = "", output_path: str = "") -> str:
    """Export เป็น Wavefront .obj (Goxel รองรับ)."""
    scene = server.store.get(scene_name or None)
    path = (
        Path(output_path)
        if output_path
        else server._exports_dir() / f"{scene.name}.obj"
    )
    export_obj(scene, path, merge_boxes=False)
    return f"export .obj (no merge) -> {path} ({scene.block_count()} voxels)"


@server.mcp.tool()
def voxelforge_launch_editor() -> str:
    """
    เปิด VoxelForge Web Editor ในเบราว์เซอร์ (Three.js 3D view).

    Bridge sync อัตโนมัติผ่าน WebSocket — แก้ใน editor หรือผ่าน MCP ได้ทั้งคู่.
    """
    server._ensure_bridge()
    # Three parents up from src/voxel_forge/server_tools/ is the repository root.
    editor_dir = Path(__file__).resolve().parents[3] / "editor"
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
        "เปิด http://localhost:5173 แล้ว (ถ้ายังไม่รัน editor ให้ใช้ run-editor.bat ก่อน)\n"
        f"Bridge: ws://127.0.0.1:8765 | HTTP scene: http://127.0.0.1:{BRIDGE_HTTP_PORT}/scene"
    )
