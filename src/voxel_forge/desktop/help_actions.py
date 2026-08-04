"""Informational dialogs for the main window.

The mixin in this module is only ever combined with
:class:`voxel_forge.desktop.app.MainWindow`, whose scene it reports on.
"""

from __future__ import annotations

from PySide6.QtWidgets import QMessageBox

from voxel_forge.desktop.i18n import tr
from voxel_forge.mesh_merge import merge_stats


class HelpActionsMixin:
    """Show merge statistics, usage guidance and the about box."""

    def _show_merge_stats(self) -> None:
        """Report how far box merging reduced the current scene."""
        scene = self._require_scene()
        if not scene:
            return
        st = merge_stats(scene)
        QMessageBox.information(
            self,
            tr("help.merge_stats_title"),
            tr(
                "help.merge_stats_body",
                name=scene.name,
                voxels=st["voxels"],
                parts=st["merged_boxes"],
                saved=st["parts_saved"],
                reduction=st["reduction_percent"],
            ),
        )

    def _usage_guide(self) -> None:
        """Show the short guide to building and exporting a scene."""
        QMessageBox.information(self, tr("help.guide_title"), tr("help.guide_body"))

    def _shortcuts_help(self) -> None:
        """List the keyboard and mouse bindings."""
        QMessageBox.information(self, tr("help.shortcuts"), tr("help.shortcuts_body"))

    def _about(self) -> None:
        """Show the product summary and the formats it exports."""
        QMessageBox.about(self, "VoxelForge", tr("help.about_body"))
