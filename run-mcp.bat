@echo off
cd /d "%~dp0"
uv sync --locked || exit /b 1
uv run voxel-forge-mcp
exit /b %errorlevel%
