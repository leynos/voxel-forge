"""Recoverable editor, desktop, preview, and VOX boundary regressions."""

from __future__ import annotations

import asyncio
import importlib
import json
import struct
import sys
import typing as typ
from types import SimpleNamespace
from unittest import mock

import pytest
from readiness_helpers import EditorSocket

from voxel_forge import bridge, vox_io
from voxel_forge.desktop import shell
from voxel_forge.model import SceneStore, VoxelScene
from voxel_forge.preview import layer_slice

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    from pathlib import Path
    from types import ModuleType


@pytest.mark.parametrize(
    ("coordinates", "error_name"),
    [
        pytest.param({"y": 0, "z": 0}, "KeyError", id="missing-coordinate"),
        pytest.param({"x": None, "y": 0, "z": 0}, "TypeError", id="null-coordinate"),
        pytest.param(
            {"x": "invalid", "y": 0, "z": 0}, "ValueError", id="invalid-coordinate"
        ),
    ],
)
def test_malformed_editor_edit_keeps_connection_usable(
    editor_bridge: tuple[SceneStore, asyncio.Queue[dict[str, typ.Any]]],
    capsys: pytest.CaptureFixture[str],
    coordinates: dict[str, int | str | None],
    error_name: str,
) -> None:
    """A rejected edit must not disconnect a client or publish partial state."""
    store, broadcasts = editor_bridge
    scene = store.create("editor")
    malformed = {"type": "editor_place", "scene_name": "editor", **coordinates}
    valid = {
        "type": "editor_place",
        "scene_name": "editor",
        "x": 1,
        "y": 0,
        "z": 0,
        "color": "2",
    }

    asyncio.run(
        bridge._ws_handler(EditorSocket([json.dumps(malformed), json.dumps(valid)]))
    )

    assert scene.layer.blocks == {(1, 0, 0): "2"}, (
        "the valid edit after a rejected message must still reach the scene"
    )
    assert broadcasts.qsize() == 1, "only the successful edit may be published"
    assert broadcasts.get_nowait()["scene"] == scene.to_dict(), (
        "publication must contain the complete successful edit"
    )
    assert error_name in capsys.readouterr().err, "the rejected edit needs a diagnostic"


@pytest.fixture
def vox_actions(monkeypatch: pytest.MonkeyPatch) -> cabc.Iterator[ModuleType]:
    """Bind real export actions to isolated optional-Qt dialog doubles."""
    widgets = SimpleNamespace(
        QFileDialog=mock.Mock(spec=["getSaveFileName"]),
        QMessageBox=mock.Mock(spec=["critical", "information"]),
    )
    monkeypatch.setitem(sys.modules, "PySide6.QtWidgets", widgets)
    monkeypatch.delitem(
        sys.modules, "voxel_forge.desktop.export_actions", raising=False
    )
    yield importlib.import_module("voxel_forge.desktop.export_actions")
    sys.modules.pop("voxel_forge.desktop.export_actions", None)


@pytest.mark.parametrize(
    "error_type",
    [OSError, ValueError, None],
    ids=["write-failure", "invalid-scene", "success"],
)
def test_vox_export_reports_outcome_in_dialog(
    vox_actions: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    error_type: type[OSError] | type[ValueError] | None,
) -> None:
    """VOX export feedback distinguishes recoverable failures from completed writes."""
    scene = VoxelScene("export")
    path = str(tmp_path / "export.vox")
    vox_actions.QFileDialog.getSaveFileName.return_value = (path, "")
    monkeypatch.setattr(vox_actions, "exports_dir", lambda: tmp_path)
    message = "cannot export this scene"
    writer = mock.Mock(side_effect=error_type(message) if error_type else None)
    monkeypatch.setattr(vox_actions, "export_vox", writer)

    class Window(vox_actions.ExportActionsMixin):
        """Provide the selected scene without starting the optional GUI stack."""

        def _require_scene(self) -> VoxelScene:
            """Return the scene that the test selected."""
            return scene

    Window()._export_vox()

    writer.assert_called_once_with(scene, path)
    if error_type is None:
        vox_actions.QMessageBox.critical.assert_not_called()
        assert vox_actions.QMessageBox.information.call_args.args[-1] == path, (
            "a completed export must identify its destination"
        )
    else:
        assert vox_actions.QMessageBox.critical.call_count == 1, (
            "an export failure must show one error dialog"
        )
        assert vox_actions.QMessageBox.critical.call_args.args[-1] == message, (
            "the error dialog must explain why export failed"
        )
        vox_actions.QMessageBox.information.assert_not_called()


@pytest.mark.parametrize(
    "outcome",
    [FileNotFoundError("explorer is unavailable"), 1, 0],
    ids=["missing-browser", "browser-failure", "browser-success"],
)
def test_folder_browser_failures_do_not_interrupt_editing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, outcome: OSError | int
) -> None:
    """Optional file-browser launch failures must never escape into an action."""
    launch = mock.Mock()
    if isinstance(outcome, OSError):
        launch.side_effect = outcome
    else:
        launch.return_value = SimpleNamespace(returncode=outcome)
    monkeypatch.setattr(shell.subprocess, "run", launch)

    shell.open_folder(tmp_path)

    launch.assert_called_once_with(["explorer", str(tmp_path)], check=False)


def test_slice_displays_negative_z_voxels() -> None:
    """Slices must include occupied negative-Z rows and their lower padding."""
    scene = VoxelScene("negative")
    scene.place(0, 0, -1, "2")

    rows = layer_slice(scene, 0).splitlines()

    occupied_row = next(row for row in rows if row.startswith("z-1 "))
    assert "2 " in occupied_row, "the negative-Z voxel must appear in its row"
    assert any(row.startswith("z-2 ") for row in rows), (
        "the slice must include padding below its negative-Z bound"
    )


@pytest.mark.parametrize(
    "payload",
    [b"", b"\x01\x00\x00", struct.pack("<I", 1), struct.pack("<I3B", 1, 0, 0, 0)],
    ids=["empty-header", "short-header", "missing-record", "short-record"],
)
def test_xyzi_truncation_has_semantic_error(payload: bytes) -> None:
    """Malformed chunk data must raise ValueError before accumulating voxels."""
    contents = vox_io._VoxContents()

    with pytest.raises(ValueError, match=r"^XYZI chunk is truncated$"):
        vox_io._read_xyzi_chunk(payload, contents)

    assert not contents.voxels, "truncated input must not accumulate partial voxels"


@pytest.mark.parametrize("records", [[], [(1, 2, 3, 4)]], ids=["empty", "one-voxel"])
def test_xyzi_complete_records_are_decoded(
    records: list[tuple[int, int, int, int]],
) -> None:
    """Complete declared voxel records retain their coordinates and palette index."""
    payload = struct.pack("<I", len(records)) + b"".join(
        struct.pack("<4B", *record) for record in records
    )
    contents = vox_io._VoxContents()

    vox_io._read_xyzi_chunk(payload, contents)

    assert contents.voxels == records, "complete records must retain their wire values"
