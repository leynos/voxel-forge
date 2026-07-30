"""Scene file actions for the main window.

The mixin in this module is only ever combined with
:class:`voxel_forge.desktop.app.MainWindow`, whose scene state it reads
and updates.
"""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QInputDialog, QMessageBox

from voxel_forge.desktop.paths import exports_dir, scenes_dir
from voxel_forge.model import VoxelScene
from voxel_forge.vox_io import import_vox

STATUS_TIMEOUT_MS = 4000


def _load_scene(path: Path) -> VoxelScene:
    """Read a scene from a supported file, by extension.

    Parameters
    ----------
    path
        File to read; either a VoxelForge ``.json`` scene or a ``.vox``
        model.

    Raises
    ------
    ValueError
        If the extension is neither ``.json`` nor ``.vox``.
    """
    match path.suffix.lower():
        case ".json":
            payload = json.loads(path.read_text(encoding="utf-8"))
            scene = VoxelScene.from_dict(payload)
        case ".vox":
            scene = import_vox(path)
        case _:
            msg = "รองรับเฉพาะ .json และ .vox"
            raise ValueError(msg)
    return scene


class FileActionsMixin:
    """Create, open, save and import scenes."""

    def open_path(self, path_str: str) -> None:
        """Load the scene at a path, reporting failures in a dialog.

        Parameters
        ----------
        path_str
            Path to a ``.json`` scene or a ``.vox`` model.
        """
        path = Path(path_str)
        try:
            self._set_scene(_load_scene(path), path)
        except Exception as exc:  # ruff: ignore[blind-except]  # Report any failure to the user.
            QMessageBox.critical(self, "เปิดไม่สำเร็จ", str(exc))

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
            self.open_path(path_str)

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
        self._status.showMessage(f"บันทึกแล้ว: {self._path}", STATUS_TIMEOUT_MS)

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
        path.write_text(
            json.dumps(scene.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        self._path = path
        self._push_recent(path)
        self._update_ui()
        self._status.showMessage(f"บันทึกแล้ว: {path}", STATUS_TIMEOUT_MS)

    def _import_vox(self) -> None:
        path_str, _ = QFileDialog.getOpenFileName(
            self, "นำเข้า .vox", str(exports_dir()), "VOX (*.vox);;All (*.*)"
        )
        if not path_str:
            return
        try:
            self._set_scene(import_vox(path_str))
        except Exception as exc:  # ruff: ignore[blind-except]  # Report any failure to the user.
            QMessageBox.critical(self, "นำเข้าไม่สำเร็จ", str(exc))
