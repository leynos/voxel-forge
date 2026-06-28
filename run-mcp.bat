@echo off
cd /d "%~dp0"
uv sync
uv run python src/voxel_forge/server.py
