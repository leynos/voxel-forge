"""Menu bar and toolbar construction for the main window.

The mixin in this module is only ever combined with
:class:`voxel_forge.desktop.app.MainWindow`; it reads that window's
action handlers and viewport when wiring the menus.
"""

from __future__ import annotations

import typing as typ

from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QToolBar

from voxel_forge.desktop.i18n import tr
from voxel_forge.desktop.paths import blender_exports_dir, exports_dir, scenes_dir
from voxel_forge.desktop.shell import open_folder

if typ.TYPE_CHECKING:
    from PySide6.QtWidgets import QMenu, QMenuBar

TREE_PRESETS = (
    (2, "create.tree_medium"),
    (3, "create.tree_detailed"),
    (4, "create.tree_tall"),
)
BEAR_PRESETS = (
    (2, "create.bear_coarse"),
    (3, "create.bear_normal"),
    (4, "create.bear_detailed"),
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
        file_menu = menu_bar.addMenu(tr("menu.file"))

        self._act_new = QAction(tr("action.new_scene"), self)
        self._act_new.setShortcut(QKeySequence.StandardKey.New)
        self._act_new.triggered.connect(self._new_scene)
        file_menu.addAction(self._act_new)

        self._act_open = QAction(tr("action.open"), self)
        self._act_open.setShortcut(QKeySequence.StandardKey.Open)
        self._act_open.triggered.connect(self._open_scene)
        file_menu.addAction(self._act_open)

        self._recent_menu = file_menu.addMenu(tr("menu.open_recent"))
        file_menu.addSeparator()

        self._act_save = QAction(tr("action.save"), self)
        self._act_save.setShortcut(QKeySequence.StandardKey.Save)
        self._act_save.triggered.connect(self._save_scene)
        file_menu.addAction(self._act_save)

        self._act_save_as = QAction(tr("action.save_as"), self)
        self._act_save_as.setShortcut(QKeySequence("Ctrl+Shift+S"))
        self._act_save_as.triggered.connect(self._save_scene_as)
        file_menu.addAction(self._act_save_as)

        file_menu.addSeparator()

        act_import = QAction(tr("action.import_vox"), self)
        act_import.triggered.connect(self._import_vox)
        file_menu.addAction(act_import)

        self._build_export_menu(file_menu)
        self._build_folder_menu(file_menu)

        file_menu.addSeparator()
        act_quit = QAction(tr("action.quit"), self)
        act_quit.setShortcut(QKeySequence.StandardKey.Quit)
        act_quit.triggered.connect(self.close)
        file_menu.addAction(act_quit)

    def _build_export_menu(self, file_menu: QMenu) -> None:
        export_menu = file_menu.addMenu(tr("menu.export"))
        for label, handler, shortcut in (
            (tr("export.blender_merged"), self._export_blender_quick, "Ctrl+E"),
            (tr("export.obj_per_voxel"), self._export_obj_raw, ""),
            (tr("export.vox"), self._export_vox, ""),
            (tr("export.roblox"), self._export_roblox, ""),
        ):
            act = QAction(label, self)
            act.triggered.connect(handler)
            if shortcut:
                act.setShortcut(QKeySequence(shortcut))
            export_menu.addAction(act)

    def _build_folder_menu(self, file_menu: QMenu) -> None:
        folder_menu = file_menu.addMenu(tr("menu.open_folder"))
        for label, path_fn in (
            (tr("folder.scenes"), scenes_dir),
            (tr("folder.exports"), exports_dir),
            (tr("folder.blender"), blender_exports_dir),
        ):
            act = QAction(label, self)
            act.triggered.connect(lambda _=False, fn=path_fn: open_folder(fn()))
            folder_menu.addAction(act)

    def _build_create_menu(self, menu_bar: QMenuBar) -> None:
        create_menu = menu_bar.addMenu(tr("menu.create"))

        tree_menu = create_menu.addMenu(tr("create.tree_menu"))
        for res, label_key in TREE_PRESETS:
            act = QAction(tr(label_key), self)
            act.triggered.connect(lambda _=False, r=res: self._build_tree_preset(r))
            tree_menu.addAction(act)
        act_tree_custom = QAction(tr("create.tree_custom"), self)
        act_tree_custom.triggered.connect(self._build_tree)
        tree_menu.addAction(act_tree_custom)

        bear_menu = create_menu.addMenu(tr("create.bear_menu"))
        for res, label_key in BEAR_PRESETS:
            act = QAction(tr(label_key), self)
            act.triggered.connect(lambda _=False, r=res: self._build_bear_preset(r))
            bear_menu.addAction(act)
        act_bear_custom = QAction(tr("create.bear_custom"), self)
        act_bear_custom.triggered.connect(self._build_chibi_bear)
        bear_menu.addAction(act_bear_custom)

    def _build_view_menu(self, menu_bar: QMenuBar) -> None:
        view_menu = menu_bar.addMenu(tr("menu.view"))
        act_frame = QAction(tr("view.frame"), self)
        act_frame.setShortcut(QKeySequence("F"))
        act_frame.triggered.connect(self._viewport.reset_camera)
        view_menu.addAction(act_frame)

        act_refresh = QAction(tr("view.refresh"), self)
        act_refresh.setShortcut(QKeySequence("R"))
        act_refresh.triggered.connect(self._refresh_view)
        view_menu.addAction(act_refresh)

    def _build_tools_menu(self, menu_bar: QMenuBar) -> None:
        tools_menu = menu_bar.addMenu(tr("menu.tools"))
        act_stats = QAction(tr("tools.merge_stats"), self)
        act_stats.triggered.connect(self._show_merge_stats)
        tools_menu.addAction(act_stats)

    def _build_help_menu(self, menu_bar: QMenuBar) -> None:
        help_menu = menu_bar.addMenu(tr("menu.help"))
        act_guide = QAction(tr("help.guide"), self)
        act_guide.triggered.connect(self._usage_guide)
        help_menu.addAction(act_guide)

        act_shortcuts = QAction(tr("help.shortcuts"), self)
        act_shortcuts.triggered.connect(self._shortcuts_help)
        help_menu.addAction(act_shortcuts)

        act_about = QAction(tr("help.about"), self)
        act_about.triggered.connect(self._about)
        help_menu.addAction(act_about)

    def _build_toolbars(self) -> None:
        main = QToolBar(tr("toolbar.main"))
        main.setMovable(False)
        self.addToolBar(main)
        for act in (self._act_new, self._act_open, self._act_save):
            main.addAction(act)
        main.addSeparator()
        main.addAction(tr("create.tree_menu"), self._build_tree)
        main.addAction(tr("toolbar.bear"), self._build_chibi_bear)
        main.addSeparator()
        act_blender = QAction(tr("toolbar.export_blender"), self)
        act_blender.triggered.connect(self._export_blender_quick)
        main.addAction(act_blender)
        main.addAction(tr("toolbar.frame"), self._viewport.reset_camera)
