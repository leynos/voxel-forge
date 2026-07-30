"""Procedural model creation actions for the main window.

The mixin in this module is only ever combined with
:class:`voxel_forge.desktop.app.MainWindow`, which owns the scene it
replaces.
"""

from __future__ import annotations

from PySide6.QtWidgets import QInputDialog, QMessageBox

from voxel_forge.procedural import build_chibi_bear, build_tree


class CreateActionsMixin:
    """Build procedural scenes from presets or from prompted parameters."""

    def _build_tree_preset(self, resolution: int) -> None:
        try:
            self._set_scene(build_tree("tree", resolution=resolution))
        except Exception as exc:  # ruff: ignore[blind-except]  # Report any failure to the user.
            QMessageBox.critical(self, "สร้างไม่สำเร็จ", str(exc))

    def _build_bear_preset(self, resolution: int) -> None:
        try:
            self._set_scene(build_chibi_bear("chibi_bear", resolution=resolution))
        except Exception as exc:  # ruff: ignore[blind-except]  # Report any failure to the user.
            QMessageBox.critical(self, "สร้างไม่สำเร็จ", str(exc))

    def _build_tree(self) -> None:
        name, ok = QInputDialog.getText(self, "ต้นไม้", "ชื่อ:", text="tree")
        if not ok or not name.strip():
            return
        resolution, ok = QInputDialog.getInt(self, "ต้นไม้", "Resolution (1-8):", 4, 1, 8)
        if not ok:
            return
        try:
            self._set_scene(build_tree(name.strip(), resolution=resolution))
        except Exception as exc:  # ruff: ignore[blind-except]  # Report any failure to the user.
            QMessageBox.critical(self, "สร้างไม่สำเร็จ", str(exc))

    def _build_chibi_bear(self) -> None:
        name, ok = QInputDialog.getText(self, "หมี Chibi", "ชื่อ:", text="chibi_bear")
        if not ok or not name.strip():
            return
        resolution, ok = QInputDialog.getInt(
            self, "หมี Chibi", "Resolution (2-6):", 3, 2, 6
        )
        if not ok:
            return
        try:
            self._set_scene(build_chibi_bear(name.strip(), resolution=resolution))
        except Exception as exc:  # ruff: ignore[blind-except]  # Report any failure to the user.
            QMessageBox.critical(self, "สร้างไม่สำเร็จ", str(exc))
