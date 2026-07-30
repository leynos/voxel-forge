@echo off
cd /d "%~dp0editor"
if not exist node_modules (
  echo Installing editor dependencies...
  call bun install
)
start "" cmd /c "cd /d %~dp0 && uv run voxel-forge-bridge"
timeout /t 2 /nobreak >nul
call bun run dev
