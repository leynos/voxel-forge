@echo off
cd /d "%~dp0"
uv sync --locked
uv run voxel-forge-mcp
