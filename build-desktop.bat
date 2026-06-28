@echo off
cd /d "%~dp0"
echo Installing desktop dependencies...
uv sync --extra desktop
echo.
echo Building VoxelForge.exe (one-folder)...
uv run pyinstaller VoxelForge.spec --noconfirm
echo.
if exist "dist\VoxelForge\VoxelForge.exe" (
    echo Done: dist\VoxelForge\VoxelForge.exe
    explorer dist\VoxelForge
) else (
    echo Build failed — check output above.
    exit /b 1
)
