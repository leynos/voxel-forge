"""Desktop application adapter (Goxel-style native window).

``app.py`` is the driving adapter that opens the desktop window, ``viewport``
renders the voxel grid, ``sidebar`` builds the palette and layer controls, and
``paths`` resolves editor asset locations. All of it is an adapter over the
domain model in :mod:`voxel_forge.model`.
"""
