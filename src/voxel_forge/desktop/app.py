"""VoxelForge Desktop — โปรแกรม voxel editor แบบ native (ไม่ใช้เบราว์เซอร์)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QDockWidget,
    QFileDialog,
    QInputDialog,
    QMainWindow,
    QMessageBox,
    QStatusBar,
    QToolBar,
)

from ..export_roblox import write_luau_file
from ..mesh_merge import merge_stats
from ..model import VoxelScene
from ..procedural import build_chibi_bear, build_tree
from ..vox_io import export_obj, export_vox, import_vox
from .paths import blender_exports_dir, exports_dir, scenes_dir
from .sidebar import SidePanel
from .viewport import VoxelViewport

MAX_RECENT = 8


class MainWindow(QMainWindow):
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
        self._sidebar.open_recent_requested.connect(self._open_path)

        self._status = QStatusBar()
        self.setStatusBar(self._status)

        self._build_menus()
        self._build_toolbars()
        self._refresh_recent_menu()
        self._sidebar.set_recent_files(self._recent_paths())
        self._update_ui()

    # ── UI build ──────────────────────────────────────────────

    def _build_menus(self) -> None:
        mb = self.menuBar()

        # File
        file_menu = mb.addMenu("ไฟล์ (&F)")

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

        export_menu = file_menu.addMenu("ส่งออก (Export)")
        for label, handler, shortcut in [
            ("Blender — .obj รวม mesh (แนะนำ)", self._export_blender_quick, "Ctrl+E"),
            ("Blender — .obj ทุก voxel (หนัก)", self._export_obj_raw, ""),
            (".vox (MagicaVoxel)", self._export_vox, ""),
            ("Roblox — Luau รวม Part", self._export_roblox, ""),
        ]:
            act = QAction(label, self)
            act.triggered.connect(handler)
            if shortcut:
                act.setShortcut(QKeySequence(shortcut))
            export_menu.addAction(act)

        folder_menu = file_menu.addMenu("เปิดโฟลเดอร์")
        for label, path_fn in [
            ("โฟลเดอร์ Scenes", scenes_dir),
            ("โฟลเดอร์ Export", exports_dir),
            ("โฟลเดอร์ Blender Export", blender_exports_dir),
        ]:
            act = QAction(label, self)
            act.triggered.connect(lambda _=False, fn=path_fn: self._open_folder(fn()))
            folder_menu.addAction(act)

        file_menu.addSeparator()
        act_quit = QAction("ออก", self)
        act_quit.setShortcut(QKeySequence.StandardKey.Quit)
        act_quit.triggered.connect(self.close)
        file_menu.addAction(act_quit)

        # Create
        create_menu = mb.addMenu("สร้าง (&C)")

        tree_menu = create_menu.addMenu("ต้นไม้")
        for res, label in [(2, "ต้นไม้ — ปานกลาง (2x)"), (3, "ต้นไม้ — ละเอียด (3x)"), (4, "ต้นไม้ — สูง (4x)")]:
            act = QAction(label, self)
            act.triggered.connect(lambda _=False, r=res: self._build_tree_preset(r))
            tree_menu.addAction(act)
        act_tree_custom = QAction("ต้นไม้ — กำหนดเอง...", self)
        act_tree_custom.triggered.connect(self._build_tree)
        tree_menu.addAction(act_tree_custom)

        bear_menu = create_menu.addMenu("หมี Chibi")
        for res, label in [(2, "หมี — หยาบ (2x)"), (3, "หมี — ปกติ (3x)"), (4, "หมี — ละเอียด (4x)")]:
            act = QAction(label, self)
            act.triggered.connect(lambda _=False, r=res: self._build_bear_preset(r))
            bear_menu.addAction(act)
        act_bear_custom = QAction("หมี — กำหนดเอง...", self)
        act_bear_custom.triggered.connect(self._build_chibi_bear)
        bear_menu.addAction(act_bear_custom)

        # View
        view_menu = mb.addMenu("มุมมอง (&V)")
        act_frame = QAction("จัดกล้องใหม่ (Frame)", self)
        act_frame.setShortcut(QKeySequence("F"))
        act_frame.triggered.connect(self._reset_camera)
        view_menu.addAction(act_frame)

        act_refresh = QAction("รีเฟรช 3D", self)
        act_refresh.setShortcut(QKeySequence("R"))
        act_refresh.triggered.connect(self._refresh_view)
        view_menu.addAction(act_refresh)

        # Tools
        tools_menu = mb.addMenu("เครื่องมือ (&T)")
        act_stats = QAction("สถิติ Merge (ลด mesh)", self)
        act_stats.triggered.connect(self._show_merge_stats)
        tools_menu.addAction(act_stats)

        # Help
        help_menu = mb.addMenu("ช่วยเหลือ (&H)")
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
        main.addAction("Frame (F)", self._reset_camera)

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
            empty = QAction("(ไม่มี)", self)
            empty.setEnabled(False)
            self._recent_menu.addAction(empty)
            return
        for p in recent:
            act = QAction(Path(p).stem, self)
            act.setToolTip(p)
            act.triggered.connect(lambda _=False, pt=p: self._open_path(pt))
            self._recent_menu.addAction(act)

    # ── Scene helpers ─────────────────────────────────────────

    def _require_scene(self) -> VoxelScene | None:
        if self._scene is None:
            QMessageBox.warning(self, "VoxelForge", "ยังไม่มี scene — สร้างใหม่หรือเปิดไฟล์ก่อน")
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

    def _open_folder(self, path: Path) -> None:
        subprocess.run(["explorer", str(path)], check=False)

    def _open_path(self, path_str: str) -> None:
        path = Path(path_str)
        try:
            if path.suffix.lower() == ".json":
                scene = VoxelScene.from_dict(json.loads(path.read_text(encoding="utf-8")))
                self._set_scene(scene, path)
            elif path.suffix.lower() == ".vox":
                self._set_scene(import_vox(path), path)
            else:
                raise ValueError("รองรับเฉพาะ .json และ .vox")
        except Exception as exc:
            QMessageBox.critical(self, "เปิดไม่สำเร็จ", str(exc))

    # ── File actions ──────────────────────────────────────────

    def _new_scene(self) -> None:
        name, ok = QInputDialog.getText(self, "Scene ใหม่", "ชื่อ scene:", text="my_model")
        if not ok or not name.strip():
            return
        self._set_scene(VoxelScene(name=name.strip()))

    def _open_scene(self) -> None:
        path_str, _ = QFileDialog.getOpenFileName(
            self,
            "เปิด Scene",
            str(scenes_dir()),
            "VoxelForge (*.json);;MagicaVoxel (*.vox);;All (*.*)",
        )
        if path_str:
            self._open_path(path_str)

    def _save_scene(self) -> None:
        scene = self._require_scene()
        if not scene:
            return
        if self._path is None:
            self._save_scene_as()
            return
        self._path.write_text(
            json.dumps(scene.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        scenes_dir()  # ensure exists
        self._update_ui()
        self._status.showMessage(f"บันทึกแล้ว: {self._path}", 4000)

    def _save_scene_as(self) -> None:
        scene = self._require_scene()
        if not scene:
            return
        path_str, _ = QFileDialog.getSaveFileName(
            self,
            "บันทึก Scene",
            str(scenes_dir() / f"{scene.name}.json"),
            "VoxelForge Scene (*.json)",
        )
        if not path_str:
            return
        path = Path(path_str)
        scene.name = path.stem
        path.write_text(json.dumps(scene.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        self._path = path
        self._push_recent(path)
        self._update_ui()
        self._status.showMessage(f"บันทึกแล้ว: {path}", 4000)

    def _import_vox(self) -> None:
        path_str, _ = QFileDialog.getOpenFileName(
            self, "นำเข้า .vox", str(exports_dir()), "VOX (*.vox);;All (*.*)"
        )
        if not path_str:
            return
        try:
            self._set_scene(import_vox(path_str))
        except Exception as exc:
            QMessageBox.critical(self, "นำเข้าไม่สำเร็จ", str(exc))

    # ── Export ────────────────────────────────────────────────

    def _export_blender_quick(self) -> None:
        scene = self._require_scene()
        if not scene:
            return
        out = blender_exports_dir() / f"{scene.name}_merged.obj"
        export_obj(scene, out, merge_boxes=True)
        st = merge_stats(scene)
        QMessageBox.information(
            self,
            "Export Blender สำเร็จ",
            f"ไฟล์: {out}\n\n"
            f"{st['voxels']} voxels → {st['merged_boxes']} mesh parts\n"
            f"ลด mesh {st['reduction_percent']}%\n\n"
            "Blender: File → Import → Wavefront (.obj)",
        )
        self._open_folder(blender_exports_dir())

    def _export_obj_raw(self) -> None:
        scene = self._require_scene()
        if not scene:
            return
        out = blender_exports_dir() / f"{scene.name}_per_voxel.obj"
        export_obj(scene, out, merge_boxes=False)
        QMessageBox.information(self, "Export สำเร็จ", str(out))

    def _export_vox(self) -> None:
        scene = self._require_scene()
        if not scene:
            return
        path_str, _ = QFileDialog.getSaveFileName(
            self,
            "Export .vox",
            str(exports_dir() / f"{scene.name}.vox"),
            "MagicaVoxel (*.vox)",
        )
        if not path_str:
            return
        export_vox(scene, path_str)
        QMessageBox.information(self, "Export สำเร็จ", path_str)

    def _export_roblox(self) -> None:
        scene = self._require_scene()
        if not scene:
            return
        path = write_luau_file(scene, exports_dir())
        st = merge_stats(scene)
        QMessageBox.information(
            self,
            "Export Roblox สำเร็จ",
            f"{st['merged_boxes']} Parts\n{path}\n\nใช้ Roblox Studio MCP → execute_luau",
        )

    # ── Create ────────────────────────────────────────────────

    def _build_tree_preset(self, resolution: int) -> None:
        try:
            self._set_scene(build_tree("tree", resolution=resolution))
        except Exception as exc:
            QMessageBox.critical(self, "สร้างไม่สำเร็จ", str(exc))

    def _build_bear_preset(self, resolution: int) -> None:
        try:
            self._set_scene(build_chibi_bear("chibi_bear", resolution=resolution))
        except Exception as exc:
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
        except Exception as exc:
            QMessageBox.critical(self, "สร้างไม่สำเร็จ", str(exc))

    def _build_chibi_bear(self) -> None:
        name, ok = QInputDialog.getText(self, "หมี Chibi", "ชื่อ:", text="chibi_bear")
        if not ok or not name.strip():
            return
        resolution, ok = QInputDialog.getInt(self, "หมี Chibi", "Resolution (2-6):", 3, 2, 6)
        if not ok:
            return
        try:
            self._set_scene(build_chibi_bear(name.strip(), resolution=resolution))
        except Exception as exc:
            QMessageBox.critical(self, "สร้างไม่สำเร็จ", str(exc))

    # ── View / Tools / Help ───────────────────────────────────

    def _reset_camera(self) -> None:
        self._viewport.reset_camera()

    def _refresh_view(self) -> None:
        if self._scene:
            self._viewport.load_scene(self._scene)

    def _show_merge_stats(self) -> None:
        scene = self._require_scene()
        if not scene:
            return
        st = merge_stats(scene)
        QMessageBox.information(
            self,
            "สถิติ Merge",
            f"Scene: {scene.name}\n\n"
            f"Voxels: {st['voxels']}\n"
            f"Merged parts: {st['merged_boxes']}\n"
            f"ลดได้: {st['parts_saved']} ({st['reduction_percent']}%)\n\n"
            "Export Blender ใช้ merged — เหมาะกับเกมและ Blender",
        )

    def _usage_guide(self) -> None:
        QMessageBox.information(
            self,
            "วิธีใช้งาน VoxelForge",
            "1. สร้าง → เลือก ต้นไม้ / หมี Chibi\n"
            "2. มุมมอง → F = จัดกล้อง\n"
            "3. ไฟล์ → บันทึก (.json)\n"
            "4. Export → Blender (.obj รวม mesh)\n"
            "5. Blender: File → Import → Wavefront (.obj)\n\n"
            "AI (Cursor): ใช้ MCP VoxelForge สร้าง scene\n"
            "แล้วเปิดไฟล์จากโฟลเดอร์ Scenes",
        )

    def _shortcuts_help(self) -> None:
        QMessageBox.information(
            self,
            "คีย์ลัด",
            "Ctrl+N     Scene ใหม่\n"
            "Ctrl+O     เปิด\n"
            "Ctrl+S     บันทึก\n"
            "Ctrl+Shift+S  บันทึกเป็น\n"
            "Ctrl+E     Export Blender\n"
            "F          จัดกล้อง\n"
            "R          รีเฟรช 3D\n\n"
            "เมาส์กลาง = หมุน | ล้อ = zoom",
        )

    def _about(self) -> None:
        QMessageBox.about(
            self,
            "VoxelForge",
            "VoxelForge Desktop v0.2\n\n"
            "Voxel editor แบบ Goxel + MCP สำหรับ AI\n"
            "Export: Blender (.obj), Roblox (Luau), .vox",
        )


def main() -> None:
    import sys

    app = QApplication(sys.argv)
    app.setApplicationName("VoxelForge")
    app.setOrganizationName("VoxelForge")
    win = MainWindow()

    if len(sys.argv) > 1:
        arg = Path(sys.argv[1])
        if arg.exists():
            win._open_path(str(arg))

    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
