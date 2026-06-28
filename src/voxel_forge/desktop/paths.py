"""โฟลเดอร์มาตรฐานของ VoxelForge Desktop."""

from __future__ import annotations

from pathlib import Path


def scenes_dir() -> Path:
    p = Path.home() / ".voxel-forge" / "scenes"
    p.mkdir(parents=True, exist_ok=True)
    return p


def exports_dir() -> Path:
    p = Path.home() / ".voxel-forge" / "exports"
    p.mkdir(parents=True, exist_ok=True)
    return p


def blender_exports_dir() -> Path:
    p = exports_dir() / "blender"
    p.mkdir(parents=True, exist_ok=True)
    return p
