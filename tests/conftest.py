"""Shared pytest fixtures for the VoxelForge readiness suite.

The suite must never read or write a developer's real
``~/.voxel-forge/scenes`` directory. The ``scene_directory`` fixture redirects
the persistence adapter at a temporary directory so tests can assert on saved
files without touching the home directory. Request it by name in any test that
saves, loads, or lists scenes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from voxel_forge import scene_store


@pytest.fixture
def scene_directory(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Point scene persistence at a temporary directory for one test."""
    directory = tmp_path / "scenes"
    directory.mkdir()
    monkeypatch.setattr(scene_store, "scenes_dir", lambda: directory)
    return directory
