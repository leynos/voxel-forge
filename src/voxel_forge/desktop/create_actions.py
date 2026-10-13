"""Procedural model creation actions for the main window.

The mixin is combined with ``MainWindow`` and uses its ``_set_scene`` seam.
Build options keep each model's naming and resolution defaults together;
presets and interactive creation share the same build/error boundary.
"""

from __future__ import annotations

import dataclasses
import typing as typ

from PySide6.QtWidgets import QInputDialog, QMessageBox

from voxel_forge.desktop.dialogs import prompt_scene_name
from voxel_forge.procedural import build_chibi_bear, build_tree

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    from voxel_forge.model import VoxelScene


@dataclasses.dataclass(frozen=True, slots=True)
class _BuildOptions:
    """The model builder and its name, dialog title, and resolution bounds."""

    builder: cabc.Callable[[str, int], VoxelScene]
    name: str
    title: str
    resolution: tuple[int, int, int]


_TREE = _BuildOptions(build_tree, "tree", "ต้นไม้", (4, 1, 8))
_BEAR = _BuildOptions(build_chibi_bear, "chibi_bear", "หมี Chibi", (3, 2, 6))


class CreateActionsMixin:
    """Build procedural scenes from presets or from prompted parameters."""

    def _build_model(self, options: _BuildOptions, name: str, resolution: int) -> None:
        """Replace the scene with the built model, reporting failures in a dialog."""
        try:
            self._set_scene(options.builder(name, resolution))
        except Exception as exc:  # ruff: ignore[blind-except]  # Report any failure to the user.
            QMessageBox.critical(self, "สร้างไม่สำเร็จ", str(exc))

    def _build_tree_preset(self, resolution: int) -> None:
        self._build_model(_TREE, _TREE.name, resolution)

    def _build_bear_preset(self, resolution: int) -> None:
        self._build_model(_BEAR, _BEAR.name, resolution)

    def _prompt_model(self, options: _BuildOptions) -> None:
        """Prompt for one model's name and resolution before building it."""
        name = prompt_scene_name(self, options.title, default=options.name)
        if name is None:
            return
        default, minimum, maximum = options.resolution
        resolution, accepted = QInputDialog.getInt(
            self,
            options.title,
            f"Resolution ({minimum}-{maximum}):",
            default,
            minimum,
            maximum,
        )
        if accepted:
            self._build_model(options, name, resolution)

    def _build_tree(self) -> None:
        self._prompt_model(_TREE)

    def _build_chibi_bear(self) -> None:
        self._prompt_model(_BEAR)
