"""Informational dialogs for the main window.

The mixin in this module is only ever combined with
:class:`voxel_forge.desktop.app.MainWindow`, whose scene it reports on.
"""

from __future__ import annotations

from PySide6.QtWidgets import QMessageBox

from voxel_forge.mesh_merge import merge_stats


class HelpActionsMixin:
    """Show merge statistics, usage guidance and the about box."""

    def _show_merge_stats(self) -> None:
        scene = self._require_scene()
        if not scene:
            return
        st = merge_stats(scene)
        QMessageBox.information(
            self,
            "สถิติ Merge",
            f"Scene: {scene.name}\n\n"
            f"Voxels: {st['voxels']}\n"
            f"Merged parts: {st['merged_boxes']}\n"
            f"ลดได้: {st['parts_saved']} ({st['reduction_percent']}%)\n\n"
            "Export Blender ใช้ merged — เหมาะกับเกมและ Blender",
        )

    def _usage_guide(self) -> None:
        QMessageBox.information(
            self,
            "วิธีใช้งาน VoxelForge",
            "1. สร้าง → เลือก ต้นไม้ / หมี Chibi\n"
            "2. มุมมอง → F = จัดกล้อง\n"
            "3. ไฟล์ → บันทึก (.json)\n"
            "4. Export → Blender (.obj รวม mesh)\n"
            "5. Blender: File → Import → Wavefront (.obj)\n\n"
            "AI (Cursor): ใช้ MCP VoxelForge สร้าง scene\n"
            "แล้วเปิดไฟล์จากโฟลเดอร์ Scenes",
        )

    def _shortcuts_help(self) -> None:
        QMessageBox.information(
            self,
            "คีย์ลัด",
            "Ctrl+N     Scene ใหม่\n"
            "Ctrl+O     เปิด\n"
            "Ctrl+S     บันทึก\n"
            "Ctrl+Shift+S  บันทึกเป็น\n"
            "Ctrl+E     Export Blender\n"
            "F          จัดกล้อง\n"
            "R          รีเฟรช 3D\n\n"
            "เมาส์กลาง = หมุน | ล้อ = zoom",
        )

    def _about(self) -> None:
        QMessageBox.about(
            self,
            "VoxelForge",
            "VoxelForge Desktop v0.2\n\n"
            "Voxel editor แบบ Goxel + MCP สำหรับ AI\n"
            "Export: Blender (.obj), Roblox (Luau), .vox",
        )
