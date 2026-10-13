"""Public domain model surface; disk persistence lives in scene_store.

For example, ``SceneStore().create("house")`` registers an empty scene.
"""

from .model_layer import VoxelLayer
from .model_scene import VoxelScene
from .model_validation import (
    DEFAULT_PALETTE,
    MAX_SCENE_NAME_LENGTH,
    MAX_VOXEL_SIZE,
    MIN_SCENE_NAME_LENGTH,
    MIN_VOXEL_SIZE,
    resolve_palette_colour,
    validate_scene_name,
)
from .scene_registry import SceneStore

__all__ = [
    "DEFAULT_PALETTE",
    "MAX_SCENE_NAME_LENGTH",
    "MAX_VOXEL_SIZE",
    "MIN_SCENE_NAME_LENGTH",
    "MIN_VOXEL_SIZE",
    "SceneStore",
    "VoxelLayer",
    "VoxelScene",
    "resolve_palette_colour",
    "validate_scene_name",
]
