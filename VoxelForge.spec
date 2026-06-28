# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — build VoxelForge desktop .exe on Windows."""

import sys
from pathlib import Path

block_cipher = None
root = Path(SPECPATH)

a = Analysis(
    [str(root / "src" / "voxel_forge" / "desktop" / "app.py")],
    pathex=[str(root / "src")],
    binaries=[],
    datas=[],
    hiddenimports=[
        "voxel_forge",
        "voxel_forge.model",
        "voxel_forge.mesh_merge",
        "voxel_forge.procedural",
        "voxel_forge.vox_io",
        "voxel_forge.export_roblox",
        "voxel_forge.preview",
        "PySide6.Qt3DCore",
        "PySide6.Qt3DExtras",
        "PySide6.Qt3DRender",
        "PySide6.Qt3DInput",
        "PySide6.Qt3DLogic",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["mcp", "websockets", "httpx"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="VoxelForge",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="VoxelForge",
)
