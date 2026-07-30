"""Shared fixtures for the VoxelForge test suite."""

from __future__ import annotations

import typing as typ

import pytest

from voxel_forge import model

if typ.TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def scene_directory(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Redirect scene persistence to a temporary directory and return its path."""
    directory = tmp_path / "scenes"
    directory.mkdir()
    monkeypatch.setattr(model, "_data_dir", lambda: directory)
    return directory
