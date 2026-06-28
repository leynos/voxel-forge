"""แผงด้านข้าง — ข้อมูล scene, งานล่าสุด, ปุ่มลัด."""

from __future__ import annotations

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

from ..mesh_merge import merge_stats
from ..model import VoxelScene
from .paths import blender_exports_dir, exports_dir, scenes_dir


class SidePanel(QWidget):
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
        root.addWidget(quick)

        create = QGroupBox("สร้างด่วน")
        cl = QVBoxLayout(create)
        btn_tree = QPushButton("ต้นไม้")
        btn_tree.clicked.connect(self.build_tree.emit)
        btn_bear = QPushButton("หมี Chibi")
        btn_bear.clicked.connect(self.build_bear.emit)
        cl.addWidget(btn_tree)
        cl.addWidget(btn_bear)
        root.addWidget(create)

        recent_box = QGroupBox("เปิดล่าสุด")
        rl = QVBoxLayout(recent_box)
        self._recent = QListWidget()
        self._recent.itemDoubleClicked.connect(self._on_recent_double)
        rl.addWidget(self._recent)
        root.addWidget(recent_box)

        folders = QGroupBox("โฟลเดอร์")
        fl = QVBoxLayout(folders)
        row = QHBoxLayout()
        for label, path in [
            ("Scenes", scenes_dir()),
            ("Export", exports_dir()),
            ("Blender", blender_exports_dir()),
        ]:
            b = QPushButton(label)
            p = str(path)
            b.setToolTip(p)
            b.clicked.connect(lambda _=False, pt=p: __import__("subprocess").run(["explorer", pt], check=False))
            row.addWidget(b)
        fl.addLayout(row)
        root.addWidget(folders)

        hint = QLabel("เมาส์กลาง = หมุน | ล้อ = zoom")
        hint.setStyleSheet("color: #888; font-size: 11px;")
        hint.setWordWrap(True)
        root.addWidget(hint)
        root.addStretch()

    def _on_recent_double(self, item: QListWidgetItem) -> None:
        path = item.data(Qt.ItemDataRole.UserRole)
        if path:
            self.open_recent_requested.emit(str(path))

    def set_scene_info(self, scene: VoxelScene | None, path: Path | None) -> None:
        if not scene:
            self._info.setText("ยังไม่มี scene\n\nกด เปิดไฟล์ หรือ สร้างด่วน")
            return
        st = merge_stats(scene)
        loc = str(path) if path else "(ยังไม่ได้บันทึก)"
        detail = int(round(1 / scene.voxel_size)) if scene.voxel_size else 1
        self._info.setText(
            f"<b>{scene.name}</b><br>"
            f"voxels: {st['voxels']}<br>"
            f"merged parts: {st['merged_boxes']}<br>"
            f"ลด mesh: {st['reduction_percent']}%<br>"
            f"ความละเอียด: {detail}x<br>"
            f"<span style='color:#999'>{loc}</span>"
        )

    def set_recent_files(self, paths: list[str]) -> None:
        self._recent.clear()
        for p in paths:
            item = QListWidgetItem(Path(p).stem)
            item.setToolTip(p)
            item.setData(Qt.ItemDataRole.UserRole, p)
            self._recent.addItem(item)
