"""Desktop creation contracts without installing the optional GUI stack."""

from __future__ import annotations

import dataclasses
import importlib
import sys
import typing as typ
from types import ModuleType, SimpleNamespace
from unittest import mock

import pytest

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    from pathlib import Path

    from voxel_forge.model import VoxelScene


@dataclasses.dataclass(frozen=True, slots=True)
class _ExportCase:
    """Expected action, filename suffix, and vertex count for one mesh mode."""

    mode: str
    suffix: str
    vertices: int


@pytest.fixture
def desktop_actions() -> cabc.Iterator[ModuleType]:
    """Import real creation actions with only their Qt dialog boundary replaced."""
    widgets = SimpleNamespace(
        QInputDialog=SimpleNamespace(getText=mock.Mock(), getInt=mock.Mock()),
        QFileDialog=mock.Mock(spec=["getSaveFileName"]),
        QMessageBox=mock.Mock(spec=["critical", "information", "about"]),
    )
    with mock.patch.dict(sys.modules, {"PySide6.QtWidgets": widgets}):
        # Import fresh bindings even when a prior test loaded the optional stack.
        for name in (
            "voxel_forge.desktop.dialogs",
            "voxel_forge.desktop.create_actions",
        ):
            sys.modules.pop(name, None)
        yield importlib.import_module("voxel_forge.desktop.create_actions")


@pytest.mark.parametrize(
    ("name", "accepted", "expected"),
    [(" tree ", True, "tree"), ("   ", True, None), ("tree", False, None)],
)
def test_scene_name_prompt_normalizes_only_accepted_input(
    desktop_actions: ModuleType, name: str, *, accepted: bool, expected: str | None
) -> None:
    """Name prompts must strip input and preserve cancellation and blank rejection."""
    desktop_actions.QInputDialog.getText.return_value = name, accepted

    result = desktop_actions.prompt_scene_name(object(), "Create", default="tree")

    assert result == expected, "the prompt must return a usable accepted name or None"


@pytest.mark.parametrize(
    "case",
    [
        ("_build_tree", "tree", 1, (4, 1, 8)),
        ("_build_chibi_bear", "chibi_bear", 2, (3, 2, 6)),
    ],
)
def test_prompted_models_keep_their_defaults_and_resolution(
    desktop_actions: ModuleType, case: tuple[str, str, int, tuple[int, int, int]]
) -> None:
    """Both UI actions must keep their own dialog bounds and build a named scene."""
    action, model_name, resolution, bounds = case

    class Window(desktop_actions.CreateActionsMixin):
        """Capture scene replacement at the real mixin's window seam."""

        scene: VoxelScene | None = None

        def _set_scene(self, scene: VoxelScene) -> None:
            """Record the scene that the prompted action builds."""
            self.scene = scene

    window = Window()
    desktop_actions.QInputDialog.getText.return_value = f" {model_name} ", True
    desktop_actions.QInputDialog.getInt.return_value = resolution, True

    actions = {
        "_build_tree": window._build_tree,
        "_build_chibi_bear": window._build_chibi_bear,
    }
    actions[action]()

    assert window.scene is not None, "accepting both prompts must build a scene"
    assert window.scene.name == model_name, "the accepted scene name must be stripped"
    assert window.scene.voxel_size == pytest.approx(1 / resolution), (
        "the chosen resolution must apply"
    )
    assert desktop_actions.QInputDialog.getInt.call_args.args[-3:] == bounds, (
        "each model must keep its own default and supported resolution range"
    )


def test_cancelled_resolution_does_not_replace_scene(
    desktop_actions: ModuleType,
) -> None:
    """Cancelling the second prompt must leave the current scene intact."""
    window = mock.Mock(spec=desktop_actions.CreateActionsMixin)
    desktop_actions.QInputDialog.getText.return_value = "tree", True
    desktop_actions.QInputDialog.getInt.return_value = 1, False

    desktop_actions.CreateActionsMixin._prompt_model(window, desktop_actions._TREE)

    window._build_model.assert_not_called()


@pytest.mark.parametrize(
    "case", [_ExportCase("merged", "merged", 8), _ExportCase("raw", "per_voxel", 16)]
)
def test_blender_exports_keep_mesh_modes_and_destinations(
    desktop_actions: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    case: _ExportCase,
) -> None:
    """Merged and raw UI exports must retain their geometry, paths, and feedback."""
    from voxel_forge.model import VoxelScene

    actions = importlib.import_module("voxel_forge.desktop.export_actions")
    scene = VoxelScene("export")
    scene.fill_box(0, 1, 0, 0, 0, 0)
    monkeypatch.setattr(actions, "blender_exports_dir", lambda: tmp_path)
    folder = mock.Mock()
    monkeypatch.setattr(actions, "open_folder", folder)

    class Window(actions.ExportActionsMixin):
        """Supply the current scene without constructing a Qt window."""

        def _require_scene(self) -> VoxelScene:
            """Return the scene that the test selected."""
            return scene

    match case.mode:
        case "merged":
            Window()._export_blender_quick()
        case "raw":
            Window()._export_obj_raw()

    destination = tmp_path / f"export_{case.suffix}.obj"
    assert (
        sum(
            line.startswith("v ")
            for line in destination.read_text(encoding="utf-8").splitlines()
        )
        == case.vertices
    ), "only the merged action may combine neighbouring voxels into one box"
    assert (
        str(destination) in desktop_actions.QMessageBox.information.call_args.args[-1]
    ), "the dialog must report the written destination"
    assert folder.call_count == int(case.mode == "merged"), (
        "only the quick merged export may reveal its output folder"
    )


@pytest.mark.parametrize(
    "case",
    [("usage", "วิธีใช้งาน VoxelForge", "1. สร้าง"), ("shortcuts", "คีย์ลัด", "Ctrl+N")],
)
def test_help_topics_keep_separate_content(
    desktop_actions: ModuleType, case: tuple[str, str, str]
) -> None:
    """Usage and keyboard help must keep their own dialog titles and content."""
    actions = importlib.import_module("voxel_forge.desktop.help_actions")
    window = actions.HelpActionsMixin()
    topic, title, text = case
    callbacks = {"usage": window._usage_guide, "shortcuts": window._shortcuts_help}

    callbacks[topic]()

    args = desktop_actions.QMessageBox.information.call_args.args
    assert args[1] == title, "the selected topic must retain its title"
    assert text in args[2], "the selected topic must retain its instructions"
