"""Export actions for the main window.

The mixin in this module is only ever combined with
:class:`voxel_forge.desktop.app.MainWindow`, whose current scene it
exports.
"""

from __future__ import annotations

from PySide6.QtWidgets import QFileDialog, QMessageBox

from voxel_forge.desktop.paths import blender_exports_dir, exports_dir
from voxel_forge.desktop.shell import open_folder
from voxel_forge.export_roblox import write_luau_file
from voxel_forge.mesh_merge import merge_stats
from voxel_forge.vox_io import export_obj, export_vox


class ExportActionsMixin:
    """Write the current scene out in the supported interchange formats."""

    def _export_blender_quick(self) -> None:
        scene = self._require_scene()
        if not scene:
            return
        out = blender_exports_dir() / f"{scene.name}_merged.obj"
        export_obj(scene, out, merge_boxes=True)
        st = merge_stats(scene)
        QMessageBox.information(
            self,
            "Export Blender สำเร็จ",
            f"ไฟล์: {out}\n\n"
            f"{st['voxels']} voxels → {st['merged_boxes']} mesh parts\n"
            f"ลด mesh {st['reduction_percent']}%\n\n"
            "Blender: File → Import → Wavefront (.obj)",
        )
        open_folder(blender_exports_dir())

    def _export_obj_raw(self) -> None:
        scene = self._require_scene()
        if not scene:
            return
        out = blender_exports_dir() / f"{scene.name}_per_voxel.obj"
        export_obj(scene, out, merge_boxes=False)
        QMessageBox.information(self, "Export สำเร็จ", str(out))

    def _export_vox(self) -> None:
        scene = self._require_scene()
        if not scene:
            return
        path_str, _ = QFileDialog.getSaveFileName(
            self,
            "Export .vox",
            str(exports_dir() / f"{scene.name}.vox"),
            "MagicaVoxel (*.vox)",
        )
        if not path_str:
            return
        export_vox(scene, path_str)
        QMessageBox.information(self, "Export สำเร็จ", path_str)

    def _export_roblox(self) -> None:
        scene = self._require_scene()
        if not scene:
            return
        path = write_luau_file(scene, exports_dir())
        st = merge_stats(scene)
        QMessageBox.information(
            self,
            "Export Roblox สำเร็จ",
            f"{st['merged_boxes']} Parts\n{path}\n\n"
            "ใช้ Roblox Studio MCP → execute_luau",
        )
