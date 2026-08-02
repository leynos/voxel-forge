"""Bilingual message catalogue for the desktop user interface.

Every user-facing string in :mod:`voxel_forge.desktop` lives here, keyed
by a stable identifier and provided in both supported languages. Look
messages up with :func:`voxel_forge.desktop.i18n.tr`; nothing else
should read this table directly. Entries whose English and Thai texts
coincide (product names, technical labels) are still registered so the
whole surface stays translatable.
"""

from __future__ import annotations

import typing as typ

MESSAGES: typ.Final[dict[str, dict[str, str]]] = {
    # ── Main window ───────────────────────────────────────────
    "sidebar.dock_title": {"en": "Control panel", "th": "แผงควบคุม"},
    "recent.empty": {"en": "(none)", "th": "(ไม่มี)"},
    "scene.none_warning": {
        "en": "No scene yet — create a new one or open a file first",
        "th": "ยังไม่มี scene — สร้างใหม่หรือเปิดไฟล์ก่อน",
    },
    "status.ready": {
        "en": "Ready — open a file or create a new model",
        "th": "พร้อมใช้งาน — เปิดไฟล์หรือสร้างโมเดลใหม่",
    },
    "scene.unsaved": {"en": "(unsaved)", "th": "(ยังไม่ได้บันทึก)"},
    "status.scene": {
        "en": (
            "{name} | {voxels} voxels | {parts} parts | "
            "mesh reduced {reduction}% | {path}"
        ),
        "th": (
            "{name} | {voxels} voxels | {parts} parts | ลด mesh {reduction}% | {path}"
        ),
    },
    # ── Menus and toolbar ─────────────────────────────────────
    "menu.file": {"en": "&File", "th": "ไฟล์ (&F)"},
    "menu.create": {"en": "&Create", "th": "สร้าง (&C)"},
    "menu.view": {"en": "&View", "th": "มุมมอง (&V)"},
    "menu.tools": {"en": "&Tools", "th": "เครื่องมือ (&T)"},
    "menu.help": {"en": "&Help", "th": "ช่วยเหลือ (&H)"},
    "action.new_scene": {"en": "New scene", "th": "Scene ใหม่"},
    "action.open": {"en": "Open...", "th": "เปิด..."},
    "menu.open_recent": {"en": "Open recent", "th": "เปิดล่าสุด"},
    "action.save": {"en": "Save", "th": "บันทึก"},
    "action.save_as": {"en": "Save as...", "th": "บันทึกเป็น..."},
    "action.import_vox": {
        "en": "Import .vox (Goxel/MagicaVoxel)...",
        "th": "นำเข้า .vox (Goxel/MagicaVoxel)...",
    },
    "action.quit": {"en": "Quit", "th": "ออก"},
    "menu.export": {"en": "Export", "th": "ส่งออก (Export)"},
    "export.blender_merged": {
        "en": "Blender — merged-mesh .obj (recommended)",
        "th": "Blender — .obj รวม mesh (แนะนำ)",
    },
    "export.obj_per_voxel": {
        "en": "Blender — .obj with every voxel (heavy)",
        "th": "Blender — .obj ทุก voxel (หนัก)",
    },
    "export.vox": {"en": ".vox (MagicaVoxel)", "th": ".vox (MagicaVoxel)"},
    "export.roblox": {
        "en": "Roblox — Luau merged Parts",
        "th": "Roblox — Luau รวม Part",
    },
    "menu.open_folder": {"en": "Open folder", "th": "เปิดโฟลเดอร์"},
    "folder.scenes": {"en": "Scenes folder", "th": "โฟลเดอร์ Scenes"},
    "folder.exports": {"en": "Export folder", "th": "โฟลเดอร์ Export"},
    "folder.blender": {
        "en": "Blender export folder",
        "th": "โฟลเดอร์ Blender Export",
    },
    "create.tree_menu": {"en": "Tree", "th": "ต้นไม้"},
    "create.tree_medium": {
        "en": "Tree — medium (2x)",
        "th": "ต้นไม้ — ปานกลาง (2x)",
    },
    "create.tree_detailed": {
        "en": "Tree — detailed (3x)",
        "th": "ต้นไม้ — ละเอียด (3x)",
    },
    "create.tree_tall": {"en": "Tree — tall (4x)", "th": "ต้นไม้ — สูง (4x)"},
    "create.tree_custom": {
        "en": "Tree — custom...",
        "th": "ต้นไม้ — กำหนดเอง...",
    },
    "create.bear_menu": {"en": "Chibi bear", "th": "หมี Chibi"},
    "create.bear_coarse": {
        "en": "Bear — coarse (2x)",
        "th": "หมี — หยาบ (2x)",
    },
    "create.bear_normal": {
        "en": "Bear — normal (3x)",
        "th": "หมี — ปกติ (3x)",
    },
    "create.bear_detailed": {
        "en": "Bear — detailed (4x)",
        "th": "หมี — ละเอียด (4x)",
    },
    "create.bear_custom": {
        "en": "Bear — custom...",
        "th": "หมี — กำหนดเอง...",
    },
    "view.frame": {
        "en": "Reframe the camera (Frame)",
        "th": "จัดกล้องใหม่ (Frame)",
    },
    "view.refresh": {"en": "Refresh 3D", "th": "รีเฟรช 3D"},
    "tools.merge_stats": {
        "en": "Merge statistics (mesh reduction)",
        "th": "สถิติ Merge (ลด mesh)",
    },
    "help.guide": {"en": "How to use", "th": "วิธีใช้งาน"},
    "help.shortcuts": {"en": "Keyboard shortcuts", "th": "คีย์ลัด"},
    "help.about": {"en": "About VoxelForge", "th": "เกี่ยวกับ VoxelForge"},
    "toolbar.main": {"en": "Main", "th": "หลัก"},
    "toolbar.bear": {"en": "Bear", "th": "หมี"},
    "toolbar.export_blender": {"en": "Export Blender", "th": "Export Blender"},
    "toolbar.frame": {"en": "Frame (F)", "th": "Frame (F)"},
    # ── Side panel ────────────────────────────────────────────
    "sidebar.no_scene": {"en": "No scene yet", "th": "ยังไม่มี scene"},
    "sidebar.no_scene_hint": {
        "en": "No scene yet\n\nUse Open file... or Quick create",
        "th": "ยังไม่มี scene\n\nกด เปิดไฟล์ หรือ สร้างด่วน",
    },
    "sidebar.scene_info": {
        "en": (
            "<b>{name}</b><br>"
            "voxels: {voxels}<br>"
            "merged parts: {parts}<br>"
            "mesh reduced: {reduction}%<br>"
            "detail: {detail}x<br>"
            "<span style='color:#999'>{path}</span>"
        ),
        "th": (
            "<b>{name}</b><br>"
            "voxels: {voxels}<br>"
            "merged parts: {parts}<br>"
            "ลด mesh: {reduction}%<br>"
            "ความละเอียด: {detail}x<br>"
            "<span style='color:#999'>{path}</span>"
        ),
    },
    "sidebar.mouse_hint": {
        "en": "Middle mouse = orbit | wheel = zoom",
        "th": "เมาส์กลาง = หมุน | ล้อ = zoom",
    },
    "sidebar.shortcuts_box": {"en": "Shortcuts", "th": "ทางลัด"},
    "sidebar.quick_new": {"en": "+ New scene", "th": "+ Scene ใหม่"},
    "sidebar.quick_open": {"en": "Open file...", "th": "เปิดไฟล์..."},
    "sidebar.quick_export": {
        "en": "Export → Blender (.obj)",
        "th": "Export → Blender (.obj)",
    },
    "sidebar.create_box": {"en": "Quick create", "th": "สร้างด่วน"},
    "sidebar.folders_box": {"en": "Folders", "th": "โฟลเดอร์"},
    # ── File actions ──────────────────────────────────────────
    "file.unsupported": {
        "en": "Only .json and .vox are supported",
        "th": "รองรับเฉพาะ .json และ .vox",
    },
    "file.open_failed": {"en": "Open failed", "th": "เปิดไม่สำเร็จ"},
    "file.scene_name_label": {"en": "Scene name:", "th": "ชื่อ scene:"},
    "file.open_dialog": {"en": "Open scene", "th": "เปิด Scene"},
    "file.save_dialog": {"en": "Save scene", "th": "บันทึก Scene"},
    "file.saved": {"en": "Saved: {path}", "th": "บันทึกแล้ว: {path}"},
    "file.import_dialog": {"en": "Import .vox", "th": "นำเข้า .vox"},
    "file.import_failed": {"en": "Import failed", "th": "นำเข้าไม่สำเร็จ"},
    # ── Create actions ────────────────────────────────────────
    "create.failed": {"en": "Create failed", "th": "สร้างไม่สำเร็จ"},
    "create.name_label": {"en": "Name:", "th": "ชื่อ:"},
    "create.tree_resolution_label": {
        "en": "Resolution (1-8):",
        "th": "Resolution (1-8):",
    },
    "create.bear_resolution_label": {
        "en": "Resolution (2-6):",
        "th": "Resolution (2-6):",
    },
    # ── Export actions ────────────────────────────────────────
    "export.blender_done_title": {
        "en": "Blender export complete",
        "th": "Export Blender สำเร็จ",
    },
    "export.blender_done_body": {
        "en": (
            "File: {path}\n\n"
            "{voxels} voxels → {parts} mesh parts\n"
            "mesh reduced {reduction}%\n\n"
            "Blender: File → Import → Wavefront (.obj)"
        ),
        "th": (
            "ไฟล์: {path}\n\n"
            "{voxels} voxels → {parts} mesh parts\n"
            "ลด mesh {reduction}%\n\n"
            "Blender: File → Import → Wavefront (.obj)"
        ),
    },
    "export.done_title": {"en": "Export complete", "th": "Export สำเร็จ"},
    "export.vox_dialog": {"en": "Export .vox", "th": "Export .vox"},
    "export.roblox_done_title": {
        "en": "Roblox export complete",
        "th": "Export Roblox สำเร็จ",
    },
    "export.roblox_done_body": {
        "en": ("{parts} Parts\n{path}\n\nUse Roblox Studio MCP → execute_luau"),
        "th": ("{parts} Parts\n{path}\n\nใช้ Roblox Studio MCP → execute_luau"),
    },
    # ── Help dialogs ──────────────────────────────────────────
    "help.merge_stats_title": {"en": "Merge statistics", "th": "สถิติ Merge"},
    "help.merge_stats_body": {
        "en": (
            "Scene: {name}\n\n"
            "Voxels: {voxels}\n"
            "Merged parts: {parts}\n"
            "Saved: {saved} ({reduction}%)\n\n"
            "The Blender export uses the merged mesh — "
            "suited to games and Blender"
        ),
        "th": (
            "Scene: {name}\n\n"
            "Voxels: {voxels}\n"
            "Merged parts: {parts}\n"
            "ลดได้: {saved} ({reduction}%)\n\n"
            "Export Blender ใช้ merged — เหมาะกับเกมและ Blender"
        ),
    },
    "help.guide_title": {
        "en": "How to use VoxelForge",
        "th": "วิธีใช้งาน VoxelForge",
    },
    "help.guide_body": {
        "en": (
            "1. Create → choose Tree / Chibi bear\n"
            "2. View → F = frame the camera\n"
            "3. File → Save (.json)\n"
            "4. Export → Blender (merged-mesh .obj)\n"
            "5. Blender: File → Import → Wavefront (.obj)\n\n"
            "AI (Cursor): build a scene over MCP VoxelForge,\n"
            "then open the file from the Scenes folder"
        ),
        "th": (
            "1. สร้าง → เลือก ต้นไม้ / หมี Chibi\n"
            "2. มุมมอง → F = จัดกล้อง\n"
            "3. ไฟล์ → บันทึก (.json)\n"
            "4. Export → Blender (.obj รวม mesh)\n"
            "5. Blender: File → Import → Wavefront (.obj)\n\n"
            "AI (Cursor): ใช้ MCP VoxelForge สร้าง scene\n"
            "แล้วเปิดไฟล์จากโฟลเดอร์ Scenes"
        ),
    },
    "help.shortcuts_body": {
        "en": (
            "Ctrl+N     New scene\n"
            "Ctrl+O     Open\n"
            "Ctrl+S     Save\n"
            "Ctrl+Shift+S  Save as\n"
            "Ctrl+E     Export Blender\n"
            "F          Frame the camera\n"
            "R          Refresh 3D\n\n"
            "Middle mouse = orbit | wheel = zoom"
        ),
        "th": (
            "Ctrl+N     Scene ใหม่\n"
            "Ctrl+O     เปิด\n"
            "Ctrl+S     บันทึก\n"
            "Ctrl+Shift+S  บันทึกเป็น\n"
            "Ctrl+E     Export Blender\n"
            "F          จัดกล้อง\n"
            "R          รีเฟรช 3D\n\n"
            "เมาส์กลาง = หมุน | ล้อ = zoom"
        ),
    },
    "help.about_body": {
        "en": (
            "VoxelForge Desktop v0.2\n\n"
            "A Goxel-style voxel editor with MCP for AI\n"
            "Export: Blender (.obj), Roblox (Luau), .vox"
        ),
        "th": (
            "VoxelForge Desktop v0.2\n\n"
            "Voxel editor แบบ Goxel + MCP สำหรับ AI\n"
            "Export: Blender (.obj), Roblox (Luau), .vox"
        ),
    },
}
