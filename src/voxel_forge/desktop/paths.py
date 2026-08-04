"""Standard data folders for VoxelForge Desktop."""

from __future__ import annotations

from pathlib import Path


def scenes_dir() -> Path:
    """Return the directory holding saved scenes, creating it if absent."""
    p = Path.home() / ".voxel-forge" / "scenes"
    p.mkdir(parents=True, exist_ok=True)
    return p


def exports_dir() -> Path:
    """Return the directory holding exported assets, creating it if absent."""
    p = Path.home() / ".voxel-forge" / "exports"
    p.mkdir(parents=True, exist_ok=True)
    return p


def blender_exports_dir() -> Path:
    """Return the Blender export subdirectory, creating it if absent."""
    p = exports_dir() / "blender"
    p.mkdir(parents=True, exist_ok=True)
    return p
