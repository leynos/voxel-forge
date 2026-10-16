"""Scene persistence adapter — the only module that names a scene directory.

The domain model in :mod:`voxel_forge.model` is pure: it validates and mutates
scene state without touching the filesystem. This module supplies the driven
port those callers need, so path construction, directory creation, and I/O
errors live in one place that can be redirected to a temporary directory in
tests.
"""

from __future__ import annotations

import json
from pathlib import Path

from .model import VoxelScene, validate_scene_name
from .paths import APPLICATION_DIRECTORY_NAME as SCENE_DIRECTORY_NAME

SCENE_SUBDIRECTORY_NAME = "scenes"
SCENE_FILE_SUFFIX = ".json"


def scenes_dir() -> Path:
    """
    Return the directory holding saved scenes, without creating it.

    Returns
    -------
    Path
        ``~/.voxel-forge/scenes``. The path is resolved only; a caller that
        wants to write must create it through :func:`ensure_scenes_dir`, so
        listing an absent store stays a read of the filesystem.
    """
    return Path.home() / SCENE_DIRECTORY_NAME / SCENE_SUBDIRECTORY_NAME


def ensure_scenes_dir() -> Path:
    """
    Return the scene directory, creating it when absent.

    Returns
    -------
    Path
        The same path as :func:`scenes_dir`, guaranteed to exist.

    Raises
    ------
    OSError
        If the directory cannot be created.
    """
    root = scenes_dir()
    root.mkdir(parents=True, exist_ok=True)
    return root


def scene_path(name: str) -> Path:
    """
    Return the on-disk path for a named scene.

    Parameters
    ----------
    name : str
        Scene name, validated before it is used as a filename component.

    Returns
    -------
    Path
        Path inside :func:`scenes_dir`.

    Raises
    ------
    ValueError
        If ``name`` is not a safe filename component. Rejecting the name here
        is what keeps a scene name from escaping the scenes directory.
    """
    return ensure_scenes_dir() / f"{validate_scene_name(name)}{SCENE_FILE_SUFFIX}"


def save_scene(scene: VoxelScene) -> Path:
    """
    Write a scene to disk as JSON.

    Parameters
    ----------
    scene : VoxelScene
        Scene to persist.

    Returns
    -------
    Path
        The file that was written.

    Raises
    ------
    ValueError
        If the scene name is not a safe filename component.
    OSError
        If the scenes directory or the scene file cannot be written.
    """
    path = scene_path(scene.name)
    path.write_text(
        json.dumps(scene.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return path


def load_scene(name: str) -> VoxelScene:
    """
    Read a previously saved scene from disk.

    Parameters
    ----------
    name : str
        Name of the saved scene, without the ``.json`` suffix.

    Returns
    -------
    VoxelScene
        The validated scene.

    Raises
    ------
    ValueError
        If the scene name is not a safe filename component, or the file content
        fails :meth:`VoxelScene.from_dict` validation.
    FileNotFoundError
        If no scene with that name is saved.
    OSError
        If the scene file cannot be read.
    """
    path = scenes_dir() / f"{validate_scene_name(name)}{SCENE_FILE_SUFFIX}"
    if not path.is_file():
        msg = f"no scene '{name}' at {path}"
        raise FileNotFoundError(msg)
    return VoxelScene.from_dict(json.loads(path.read_text(encoding="utf-8")))


def list_saved_scenes() -> list[str]:
    """
    List the names of every saved scene, sorted for stable output.

    Listing never creates the scene directory: an absent store is simply
    empty, so a read has no filesystem side effect.

    Returns
    -------
    list[str]
        Scene names without the ``.json`` suffix, empty when the directory
        does not exist.

    Raises
    ------
    OSError
        If the scenes directory exists but cannot be read.
    """
    root = scenes_dir()
    if not root.is_dir():
        return []
    return sorted(path.stem for path in root.glob(f"*{SCENE_FILE_SUFFIX}"))
