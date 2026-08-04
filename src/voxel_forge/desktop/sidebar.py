"""Side panel showing scene details, recent files and quick actions."""

from __future__ import annotations

import typing as typ
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from voxel_forge.desktop.i18n import tr
from voxel_forge.desktop.paths import blender_exports_dir, exports_dir, scenes_dir
from voxel_forge.desktop.shell import open_folder
from voxel_forge.mesh_merge import merge_stats

if typ.TYPE_CHECKING:
    from voxel_forge.model import VoxelScene


class SidePanel(QWidget):
    """Dock panel showing scene details, recent files and quick actions."""

    open_recent_requested = Signal(str)
    quick_new = Signal()
    quick_open = Signal()
    quick_save = Signal()
    export_blender = Signal()
    build_tree = Signal()
    build_bear = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setMinimumWidth(240)
        self.setMaximumWidth(320)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)

        title = QLabel("VoxelForge")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #7fdbff;")
        root.addWidget(title)

        self._info = QLabel(tr("sidebar.no_scene"))
        self._info.setWordWrap(True)
        self._info.setStyleSheet("color: #ccc; font-size: 12px; line-height: 1.4;")
        root.addWidget(self._info)

        root.addWidget(self._build_quick_box())
        root.addWidget(self._build_create_box())
        root.addWidget(self._build_recent_box())
        root.addWidget(self._build_folders_box())

        hint = QLabel(tr("sidebar.mouse_hint"))
        hint.setStyleSheet("color: #888; font-size: 11px;")
        hint.setWordWrap(True)
        root.addWidget(hint)
        root.addStretch()

    def set_scene_info(self, scene: VoxelScene | None, path: Path | None) -> None:
        """Show a summary of the current scene, or a prompt when there is none.

        Parameters
        ----------
        scene
            Scene to summarise, or ``None`` when nothing is loaded.
        path
            File backing the scene, or ``None`` when it is unsaved.
        """
        if not scene:
            self._info.setText(tr("sidebar.no_scene_hint"))
            return
        st = merge_stats(scene)
        loc = str(path) if path else tr("scene.unsaved")
        detail = round(1 / scene.voxel_size) if scene.voxel_size else 1
        self._info.setText(
            tr(
                "sidebar.scene_info",
                name=scene.name,
                voxels=st["voxels"],
                parts=st["merged_boxes"],
                reduction=st["reduction_percent"],
                detail=detail,
                path=loc,
            )
        )

    def set_recent_files(self, paths: list[str]) -> None:
        """Replace the recent-files list.

        Parameters
        ----------
        paths
            Scene paths, most recently used first.
        """
        self._recent.clear()
        for p in paths:
            item = QListWidgetItem(Path(p).stem)
            item.setToolTip(p)
            item.setData(Qt.ItemDataRole.UserRole, p)
            self._recent.addItem(item)

    def _build_quick_box(self) -> QGroupBox:
        quick = QGroupBox(tr("sidebar.shortcuts_box"))
        ql = QVBoxLayout(quick)
        for text, slot in [
            (tr("sidebar.quick_new"), self.quick_new.emit),
            (tr("sidebar.quick_open"), self.quick_open.emit),
            (tr("action.save"), self.quick_save.emit),
            (tr("sidebar.quick_export"), self.export_blender.emit),
        ]:
            btn = QPushButton(text)
            btn.clicked.connect(slot)
            ql.addWidget(btn)
        return quick

    def _build_create_box(self) -> QGroupBox:
        create = QGroupBox(tr("sidebar.create_box"))
        cl = QVBoxLayout(create)
        btn_tree = QPushButton(tr("create.tree_menu"))
        btn_tree.clicked.connect(self.build_tree.emit)
        btn_bear = QPushButton(tr("create.bear_menu"))
        btn_bear.clicked.connect(self.build_bear.emit)
        cl.addWidget(btn_tree)
        cl.addWidget(btn_bear)
        return create

    def _build_recent_box(self) -> QGroupBox:
        recent_box = QGroupBox(tr("menu.open_recent"))
        rl = QVBoxLayout(recent_box)
        self._recent = QListWidget()
        self._recent.itemDoubleClicked.connect(self._on_recent_double)
        rl.addWidget(self._recent)
        return recent_box

    @staticmethod
    def _build_folders_box() -> QGroupBox:
        folders = QGroupBox(tr("sidebar.folders_box"))
        fl = QVBoxLayout(folders)
        row = QHBoxLayout()
        for label_key, path in [
            ("sidebar.folder_scenes", scenes_dir()),
            ("sidebar.folder_export", exports_dir()),
            ("sidebar.folder_blender", blender_exports_dir()),
        ]:
            b = QPushButton(tr(label_key))
            b.setToolTip(str(path))
            b.clicked.connect(lambda _=False, target=path: open_folder(target))
            row.addWidget(b)
        fl.addLayout(row)
        return folders

    def _on_recent_double(self, item: QListWidgetItem) -> None:
        path = item.data(Qt.ItemDataRole.UserRole)
        if path:
            self.open_recent_requested.emit(str(path))
