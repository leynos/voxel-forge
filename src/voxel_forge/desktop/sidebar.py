"""แผงด้านข้าง — ข้อมูล scene, งานล่าสุด, ปุ่มลัด."""

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

        self._info = QLabel("ยังไม่มี scene")
        self._info.setWordWrap(True)
        self._info.setStyleSheet("color: #ccc; font-size: 12px; line-height: 1.4;")
        root.addWidget(self._info)

        root.addWidget(self._build_quick_box())
        root.addWidget(self._build_create_box())
        root.addWidget(self._build_recent_box())
        root.addWidget(self._build_folders_box())

        hint = QLabel("เมาส์กลาง = หมุน | ล้อ = zoom")
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
            self._info.setText("ยังไม่มี scene\n\nกด เปิดไฟล์ หรือ สร้างด่วน")
            return
        st = merge_stats(scene)
        loc = str(path) if path else "(ยังไม่ได้บันทึก)"
        detail = round(1 / scene.voxel_size) if scene.voxel_size else 1
        self._info.setText(
            f"<b>{scene.name}</b><br>"
            f"voxels: {st['voxels']}<br>"
            f"merged parts: {st['merged_boxes']}<br>"
            f"ลด mesh: {st['reduction_percent']}%<br>"
            f"ความละเอียด: {detail}x<br>"
            f"<span style='color:#999'>{loc}</span>"
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
        quick = QGroupBox("ทางลัด")
        ql = QVBoxLayout(quick)
        for text, slot in [
            ("+ Scene ใหม่", self.quick_new.emit),
            ("เปิดไฟล์...", self.quick_open.emit),
            ("บันทึก", self.quick_save.emit),
            ("Export → Blender (.obj)", self.export_blender.emit),
        ]:
            btn = QPushButton(text)
            btn.clicked.connect(slot)
            ql.addWidget(btn)
        return quick

    def _build_create_box(self) -> QGroupBox:
        create = QGroupBox("สร้างด่วน")
        cl = QVBoxLayout(create)
        btn_tree = QPushButton("ต้นไม้")
        btn_tree.clicked.connect(self.build_tree.emit)
        btn_bear = QPushButton("หมี Chibi")
        btn_bear.clicked.connect(self.build_bear.emit)
        cl.addWidget(btn_tree)
        cl.addWidget(btn_bear)
        return create

    def _build_recent_box(self) -> QGroupBox:
        recent_box = QGroupBox("เปิดล่าสุด")
        rl = QVBoxLayout(recent_box)
        self._recent = QListWidget()
        self._recent.itemDoubleClicked.connect(self._on_recent_double)
        rl.addWidget(self._recent)
        return recent_box

    @staticmethod
    def _build_folders_box() -> QGroupBox:
        folders = QGroupBox("โฟลเดอร์")
        fl = QVBoxLayout(folders)
        row = QHBoxLayout()
        for label, path in [
            ("Scenes", scenes_dir()),
            ("Export", exports_dir()),
            ("Blender", blender_exports_dir()),
        ]:
            b = QPushButton(label)
            b.setToolTip(str(path))
            b.clicked.connect(lambda _=False, target=path: open_folder(target))
            row.addWidget(b)
        fl.addLayout(row)
        return folders

    def _on_recent_double(self, item: QListWidgetItem) -> None:
        path = item.data(Qt.ItemDataRole.UserRole)
        if path:
            self.open_recent_requested.emit(str(path))
