from __future__ import annotations

from pathlib import Path

import pytest

from voxel_forge import model


@pytest.fixture
def scene_directory(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    directory = tmp_path / "scenes"
    directory.mkdir()
    monkeypatch.setattr(model, "_data_dir", lambda: directory)
    return directory
