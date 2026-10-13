"""Application storage directories shared by desktop, MCP, and persistence.

Use these functions for VoxelForge-owned scene and export directories. For
example, ``scenes_dir()`` creates and returns ``~/.voxel-forge/scenes``;
explicit user-selected file paths remain the caller's responsibility.
"""

import functools
from pathlib import Path


def _application_directory(*parts: str) -> Path:
    """Create and return one directory below the application's home root."""
    directory = Path.home().joinpath(".voxel-forge", *parts)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


# Directory APIs bind the shared creation operation to their application scope.
scenes_dir = functools.partial(_application_directory, "scenes")
exports_dir = functools.partial(_application_directory, "exports")
blender_exports_dir = functools.partial(_application_directory, "exports", "blender")
