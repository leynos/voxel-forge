"""Desktop import surface for the application's shared storage directories.

For example, ``scenes_dir()`` returns the scene directory used by the MCP
server and scene persistence too.
"""

from voxel_forge.paths import blender_exports_dir, exports_dir, scenes_dir

__all__ = ["blender_exports_dir", "exports_dir", "scenes_dir"]
