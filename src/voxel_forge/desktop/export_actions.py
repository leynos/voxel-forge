"""Export actions for the main window.

The mixin in this module is only ever combined with
:class:`voxel_forge.desktop.app.MainWindow`, whose current scene it
exports.
"""

from __future__ import annotations

from PySide6.QtWidgets import QFileDialog, QMessageBox

from voxel_forge.desktop.i18n import tr
from voxel_forge.desktop.paths import blender_exports_dir, exports_dir
from voxel_forge.desktop.shell import open_folder
from voxel_forge.export_roblox import write_luau_file
from voxel_forge.mesh_merge import merge_stats
from voxel_forge.vox_io import export_obj, export_vox


class ExportActionsMixin:
    """Write the current scene out in the supported interchange formats."""

    def _export_blender_quick(self) -> None:
        """Export merged geometry for Blender and reveal the containing folder."""
        scene = self._require_scene()
        if not scene:
            return
        out = blender_exports_dir() / f"{scene.name}_merged.obj"
        export_obj(scene, out, merge_boxes=True)
        st = merge_stats(scene)
        QMessageBox.information(
            self,
            tr("export.blender_done_title"),
            tr(
                "export.blender_done_body",
                path=out,
                voxels=st["voxels"],
                parts=st["merged_boxes"],
                reduction=st["reduction_percent"],
            ),
        )
        open_folder(blender_exports_dir())

    def _export_obj_raw(self) -> None:
        """Export one cube per voxel, without merging, for inspection."""
        scene = self._require_scene()
        if not scene:
            return
        out = blender_exports_dir() / f"{scene.name}_per_voxel.obj"
        export_obj(scene, out, merge_boxes=False)
        QMessageBox.information(self, tr("export.done_title"), str(out))

    def _export_vox(self) -> None:
        """Ask for a destination and write the scene as MagicaVoxel .vox."""
        scene = self._require_scene()
        if not scene:
            return
        path_str, _ = QFileDialog.getSaveFileName(
            self,
            tr("export.vox_dialog"),
            str(exports_dir() / f"{scene.name}.vox"),
            tr("export.vox_filter"),
        )
        if not path_str:
            return
        export_vox(scene, path_str)
        QMessageBox.information(self, tr("export.done_title"), path_str)

    def _export_roblox(self) -> None:
        """Write a Luau script that rebuilds the merged scene in Roblox."""
        scene = self._require_scene()
        if not scene:
            return
        path = write_luau_file(scene, exports_dir())
        st = merge_stats(scene)
        QMessageBox.information(
            self,
            tr("export.roblox_done_title"),
            tr("export.roblox_done_body", parts=st["merged_boxes"], path=path),
        )
