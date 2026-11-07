"""VoxelForge Desktop — โปรแกรม voxel editor แบบ native (ไม่ใช้เบราว์เซอร์)."""

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
        """Build the viewport, side panel, menus and toolbars, then sync the UI."""
        super().__init__()
        self.setWindowTitle("VoxelForge")
        self.resize(1360, 860)

        self._settings = QSettings("VoxelForge", "Desktop")
        self._scene: VoxelScene | None = None
        self._path: Path | None = None

        self._viewport = VoxelViewport()
        self.setCentralWidget(self._viewport.embed_widget())

        self._sidebar = SidePanel()
        dock = QDockWidget("แผงควบคุม", self)
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
        """Return the stored recent paths that still exist, capped at ``MAX_RECENT``.

        A stored value that is not a list counts as no recent files.
        """
        raw = self._settings.value("recent_files", [])
        if not isinstance(raw, list):
            return []
        return [str(p) for p in raw if Path(str(p)).exists()][:MAX_RECENT]

    def _push_recent(self, path: Path) -> None:
        """Store ``path`` as the most recent file and refresh the menu and sidebar."""
        paths = [str(path)] + [p for p in self._recent_paths() if p != str(path)]
        self._settings.setValue("recent_files", paths[:MAX_RECENT])
        self._refresh_recent_menu()
        self._sidebar.set_recent_files(paths[:MAX_RECENT])

    def _refresh_recent_menu(self) -> None:
        """Rebuild the recent-files submenu from the stored paths.

        An empty list shows one disabled placeholder entry instead.
        """
        self._recent_menu.clear()
        recent = self._recent_paths()
        if not recent:
            empty = QAction("(ไม่มี)", self)
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
        """Return the current scene, or warn and return ``None`` if there is none."""
        if self._scene is None:
            QMessageBox.warning(self, "VoxelForge", "ยังไม่มี scene — สร้างใหม่หรือเปิดไฟล์ก่อน")
            return None
        return self._scene

    def _set_scene(self, scene: VoxelScene, path: Path | None = None) -> None:
        """Make ``scene`` current, then load it into the viewport.

        A given ``path`` is also recorded in the recent files.
        """
        self._scene = scene
        self._path = path
        self._viewport.load_scene(scene)
        if path:
            self._push_recent(path)
        self._update_ui()

    def _update_ui(self) -> None:
        """Refresh the side panel, status bar and window title for the scene.

        With no scene, the ready message and the plain title are shown.
        """
        self._sidebar.set_scene_info(self._scene, self._path)
        if not self._scene:
            self._status.showMessage("พร้อมใช้งาน — เปิดไฟล์หรือสร้างโมเดลใหม่")
            self.setWindowTitle("VoxelForge")
            return
        st = merge_stats(self._scene)
        path = str(self._path) if self._path else "(ยังไม่ได้บันทึก)"
        self._status.showMessage(
            f"{self._scene.name} | {st['voxels']} voxels | "
            f"{st['merged_boxes']} parts | ลด mesh {st['reduction_percent']}% | {path}"
        )
        self.setWindowTitle(f"VoxelForge — {self._scene.name}")

    # ── View ──────────────────────────────────────────────────

    def _refresh_view(self) -> None:
        """Reload the current scene into the viewport, if there is one."""
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
