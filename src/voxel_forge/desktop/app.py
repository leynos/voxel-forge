"""VoxelForge Desktop, the native voxel editor (no browser required)."""

from __future__ import annotations

import typing as typ
from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication,
    QDockWidget,
    QMainWindow,
    QMessageBox,
    QStatusBar,
)

from voxel_forge.desktop.create_actions import CreateActionsMixin
from voxel_forge.desktop.export_actions import ExportActionsMixin
from voxel_forge.desktop.file_actions import FileActionsMixin
from voxel_forge.desktop.help_actions import HelpActionsMixin
from voxel_forge.desktop.i18n import tr
from voxel_forge.desktop.menus import MenuBuilderMixin
from voxel_forge.desktop.sidebar import SidePanel
from voxel_forge.desktop.viewport import VoxelViewport
from voxel_forge.mesh_merge import merge_stats

if typ.TYPE_CHECKING:
    from voxel_forge.model import VoxelScene

MAX_RECENT = 8


class MainWindow(
    QMainWindow,
    MenuBuilderMixin,
    FileActionsMixin,
    ExportActionsMixin,
    CreateActionsMixin,
    HelpActionsMixin,
):
    """The VoxelForge editor window.

    Owns the current scene, the 3D viewport and the side panel. The menu,
    file, export, create and help behaviour lives in the mixins declared
    above, all of which read the state established here.
    """

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("VoxelForge")
        self.resize(1360, 860)

        self._settings = QSettings("VoxelForge", "Desktop")
        self._scene: VoxelScene | None = None
        self._path: Path | None = None

        self._viewport = VoxelViewport()
        self.setCentralWidget(self._viewport.embed_widget())

        self._sidebar = SidePanel()
        dock = QDockWidget(tr("sidebar.dock_title"), self)
        dock.setWidget(self._sidebar)
        dock.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)

        self._sidebar.quick_new.connect(self._new_scene)
        self._sidebar.quick_open.connect(self._open_scene)
        self._sidebar.quick_save.connect(self._save_scene)
        self._sidebar.export_blender.connect(self._export_blender_quick)
        self._sidebar.build_tree.connect(self._build_tree)
        self._sidebar.build_bear.connect(self._build_chibi_bear)
        self._sidebar.open_recent_requested.connect(self.open_path)

        self._status = QStatusBar()
        self.setStatusBar(self._status)

        self._build_menus()
        self._build_toolbars()
        self._refresh_recent_menu()
        self._sidebar.set_recent_files(self._recent_paths())
        self._update_ui()

    # ── Recent files ──────────────────────────────────────────

    def _recent_paths(self) -> list[str]:
        raw = self._settings.value("recent_files", [])
        if not isinstance(raw, list):
            return []
        return [str(p) for p in raw if Path(str(p)).exists()][:MAX_RECENT]

    def _push_recent(self, path: Path) -> None:
        paths = [str(path)] + [p for p in self._recent_paths() if p != str(path)]
        self._settings.setValue("recent_files", paths[:MAX_RECENT])
        self._refresh_recent_menu()
        self._sidebar.set_recent_files(paths[:MAX_RECENT])

    def _refresh_recent_menu(self) -> None:
        self._recent_menu.clear()
        recent = self._recent_paths()
        if not recent:
            empty = QAction(tr("recent.empty"), self)
            empty.setEnabled(False)
            self._recent_menu.addAction(empty)
            return
        for p in recent:
            act = QAction(Path(p).stem, self)
            act.setToolTip(p)
            act.triggered.connect(lambda _=False, pt=p: self.open_path(pt))
            self._recent_menu.addAction(act)

    # ── Scene helpers ─────────────────────────────────────────

    def _require_scene(self) -> VoxelScene | None:
        if self._scene is None:
            QMessageBox.warning(self, "VoxelForge", tr("scene.none_warning"))
            return None
        return self._scene

    def _set_scene(self, scene: VoxelScene, path: Path | None = None) -> None:
        self._scene = scene
        self._path = path
        self._viewport.load_scene(scene)
        if path:
            self._push_recent(path)
        self._update_ui()

    def _update_ui(self) -> None:
        self._sidebar.set_scene_info(self._scene, self._path)
        if not self._scene:
            self._status.showMessage(tr("status.ready"))
            self.setWindowTitle("VoxelForge")
            return
        st = merge_stats(self._scene)
        path = str(self._path) if self._path else tr("scene.unsaved")
        self._status.showMessage(
            tr(
                "status.scene",
                name=self._scene.name,
                voxels=st["voxels"],
                parts=st["merged_boxes"],
                reduction=st["reduction_percent"],
                path=path,
            )
        )
        self.setWindowTitle(f"VoxelForge — {self._scene.name}")

    # ── View ──────────────────────────────────────────────────

    def _refresh_view(self) -> None:
        if self._scene:
            self._viewport.load_scene(self._scene)


def main() -> None:
    """Run the desktop application, opening a scene given on the command line."""
    import sys

    app = QApplication(sys.argv)
    app.setApplicationName("VoxelForge")
    app.setOrganizationName("VoxelForge")
    win = MainWindow()

    if len(sys.argv) > 1:
        arg = Path(sys.argv[1])
        if arg.exists():
            win.open_path(str(arg))

    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
