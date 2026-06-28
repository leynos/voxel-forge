@echo off
cd /d "%~dp0"
uv sync --extra desktop
uv run voxel-forge
