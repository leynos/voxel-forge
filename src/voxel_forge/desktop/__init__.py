"""Native desktop front end for VoxelForge.

The modules in this package import PySide6 at module scope, so they are
only imported when the desktop application actually runs. Use
:mod:`voxel_forge.desktop.launch` as the entry point; it degrades
gracefully when the optional ``desktop`` extra is not installed.
"""
