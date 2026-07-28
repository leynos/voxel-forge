from __future__ import annotations

from pathlib import Path


def test_windows_mcp_launcher_uses_installed_entrypoint() -> None:
    launcher = Path("run-mcp.bat").read_text(encoding="utf-8")

    assert "uv run voxel-forge-mcp" in launcher
    assert "python src/voxel_forge/server.py" not in launcher
