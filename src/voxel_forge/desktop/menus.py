"""Menu bar and toolbar construction for the main window.

The mixin in this module is only ever combined with
:class:`voxel_forge.desktop.app.MainWindow`; it reads that window's
action handlers and viewport when wiring the menus.
"""

from __future__ import annotations

import typing as typ

from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QToolBar

from voxel_forge.desktop.paths import blender_exports_dir, exports_dir, scenes_dir
from voxel_forge.desktop.shell import open_folder

if typ.TYPE_CHECKING:
    from PySide6.QtWidgets import QMenu, QMenuBar

TREE_PRESETS = (
    (2, "ต้นไม้ — ปานกลาง (2x)"),
    (3, "ต้นไม้ — ละเอียด (3x)"),
    (4, "ต้นไม้ — สูง (4x)"),
)
BEAR_PRESETS = (
    (2, "หมี — หยาบ (2x)"),
    (3, "หมี — ปกติ (3x)"),
    (4, "หมี — ละเอียด (4x)"),
)


class MenuBuilderMixin:
    """Assemble the menu bar and the main toolbar of the editor window."""

    _act_new: QAction
    _act_open: QAction
    _act_save: QAction
    _act_save_as: QAction
    _recent_menu: QMenu

    def _build_menus(self) -> None:
        mb = self.menuBar()
        self._build_file_menu(mb)
        self._build_create_menu(mb)
        self._build_view_menu(mb)
        self._build_tools_menu(mb)
        self._build_help_menu(mb)

    def _build_file_menu(self, menu_bar: QMenuBar) -> None:
        file_menu = menu_bar.addMenu("ไฟล์ (&F)")

        self._act_new = QAction("Scene ใหม่", self)
        self._act_new.setShortcut(QKeySequence.StandardKey.New)
        self._act_new.triggered.connect(self._new_scene)
        file_menu.addAction(self._act_new)

        self._act_open = QAction("เปิด...", self)
        self._act_open.setShortcut(QKeySequence.StandardKey.Open)
        self._act_open.triggered.connect(self._open_scene)
        file_menu.addAction(self._act_open)

        self._recent_menu = file_menu.addMenu("เปิดล่าสุด")
        file_menu.addSeparator()

        self._act_save = QAction("บันทึก", self)
        self._act_save.setShortcut(QKeySequence.StandardKey.Save)
        self._act_save.triggered.connect(self._save_scene)
        file_menu.addAction(self._act_save)

        self._act_save_as = QAction("บันทึกเป็น...", self)
        self._act_save_as.setShortcut(QKeySequence("Ctrl+Shift+S"))
        self._act_save_as.triggered.connect(self._save_scene_as)
        file_menu.addAction(self._act_save_as)

        file_menu.addSeparator()

        act_import = QAction("นำเข้า .vox (Goxel/MagicaVoxel)...", self)
        act_import.triggered.connect(self._import_vox)
        file_menu.addAction(act_import)

        self._build_export_menu(file_menu)
        self._build_folder_menu(file_menu)

        file_menu.addSeparator()
        act_quit = QAction("ออก", self)
        act_quit.setShortcut(QKeySequence.StandardKey.Quit)
        act_quit.triggered.connect(self.close)
        file_menu.addAction(act_quit)

    def _build_export_menu(self, file_menu: QMenu) -> None:
        export_menu = file_menu.addMenu("ส่งออก (Export)")
        for label, handler, shortcut in (
            ("Blender — .obj รวม mesh (แนะนำ)", self._export_blender_quick, "Ctrl+E"),
            ("Blender — .obj ทุก voxel (หนัก)", self._export_obj_raw, ""),
            (".vox (MagicaVoxel)", self._export_vox, ""),
            ("Roblox — Luau รวม Part", self._export_roblox, ""),
        ):
            act = QAction(label, self)
            act.triggered.connect(handler)
            if shortcut:
                act.setShortcut(QKeySequence(shortcut))
            export_menu.addAction(act)

    def _build_folder_menu(self, file_menu: QMenu) -> None:
        folder_menu = file_menu.addMenu("เปิดโฟลเดอร์")
        for label, path_fn in (
            ("โฟลเดอร์ Scenes", scenes_dir),
            ("โฟลเดอร์ Export", exports_dir),
            ("โฟลเดอร์ Blender Export", blender_exports_dir),
        ):
            act = QAction(label, self)
            act.triggered.connect(lambda _=False, fn=path_fn: open_folder(fn()))
            folder_menu.addAction(act)

    def _build_create_menu(self, menu_bar: QMenuBar) -> None:
        create_menu = menu_bar.addMenu("สร้าง (&C)")

        tree_menu = create_menu.addMenu("ต้นไม้")
        for res, label in TREE_PRESETS:
            act = QAction(label, self)
            act.triggered.connect(lambda _=False, r=res: self._build_tree_preset(r))
            tree_menu.addAction(act)
        act_tree_custom = QAction("ต้นไม้ — กำหนดเอง...", self)
        act_tree_custom.triggered.connect(self._build_tree)
        tree_menu.addAction(act_tree_custom)

        bear_menu = create_menu.addMenu("หมี Chibi")
        for res, label in BEAR_PRESETS:
            act = QAction(label, self)
            act.triggered.connect(lambda _=False, r=res: self._build_bear_preset(r))
            bear_menu.addAction(act)
        act_bear_custom = QAction("หมี — กำหนดเอง...", self)
        act_bear_custom.triggered.connect(self._build_chibi_bear)
        bear_menu.addAction(act_bear_custom)

    def _build_view_menu(self, menu_bar: QMenuBar) -> None:
        view_menu = menu_bar.addMenu("มุมมอง (&V)")
        act_frame = QAction("จัดกล้องใหม่ (Frame)", self)
        act_frame.setShortcut(QKeySequence("F"))
        act_frame.triggered.connect(self._viewport.reset_camera)
        view_menu.addAction(act_frame)

        act_refresh = QAction("รีเฟรช 3D", self)
        act_refresh.setShortcut(QKeySequence("R"))
        act_refresh.triggered.connect(self._refresh_view)
        view_menu.addAction(act_refresh)

    def _build_tools_menu(self, menu_bar: QMenuBar) -> None:
        tools_menu = menu_bar.addMenu("เครื่องมือ (&T)")
        act_stats = QAction("สถิติ Merge (ลด mesh)", self)
        act_stats.triggered.connect(self._show_merge_stats)
        tools_menu.addAction(act_stats)

    def _build_help_menu(self, menu_bar: QMenuBar) -> None:
        help_menu = menu_bar.addMenu("ช่วยเหลือ (&H)")
        act_guide = QAction("วิธีใช้งาน", self)
        act_guide.triggered.connect(self._usage_guide)
        help_menu.addAction(act_guide)

        act_shortcuts = QAction("คีย์ลัด", self)
        act_shortcuts.triggered.connect(self._shortcuts_help)
        help_menu.addAction(act_shortcuts)

        act_about = QAction("เกี่ยวกับ VoxelForge", self)
        act_about.triggered.connect(self._about)
        help_menu.addAction(act_about)

    def _build_toolbars(self) -> None:
        main = QToolBar("หลัก")
        main.setMovable(False)
        self.addToolBar(main)
        for act in (self._act_new, self._act_open, self._act_save):
            main.addAction(act)
        main.addSeparator()
        main.addAction("ต้นไม้", self._build_tree)
        main.addAction("หมี", self._build_chibi_bear)
        main.addSeparator()
        act_blender = QAction("Export Blender", self)
        act_blender.triggered.connect(self._export_blender_quick)
        main.addAction(act_blender)
        main.addAction("Frame (F)", self._viewport.reset_camera)
