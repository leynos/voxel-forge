"""Shared pytest fixtures for the VoxelForge readiness suite.

The suite must never read or write a developer's real
``~/.voxel-forge/scenes`` directory. The ``scene_directory`` fixture redirects
the persistence adapter at a temporary directory so tests can assert on saved
files without touching the home directory. Request it by name in any test that
saves, loads, or lists scenes.
"""

from __future__ import annotations

import asyncio
import typing as typ
from pathlib import Path

import pytest

from voxel_forge import bridge, scene_store, server
from voxel_forge.model import SceneStore


@pytest.fixture
def scene_directory(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Point scene persistence at a temporary directory for one test."""
    directory = tmp_path / "scenes"
    directory.mkdir()
    monkeypatch.setattr(scene_store, "scenes_dir", lambda: directory)
    return directory


@pytest.fixture
def empty_server_store(monkeypatch: pytest.MonkeyPatch) -> SceneStore:
    """Replace the module-level scene registry and bridge sync for one test."""
    replacement = SceneStore()
    monkeypatch.setattr(server, "store", replacement)
    monkeypatch.setattr(server, "_sync_bridge", lambda _scene: None)
    return replacement


@pytest.fixture
def desktop_extra_hint() -> str:
    """Return complete user guidance shared by launcher and wheel checks."""
    return (Path(__file__).parent / "data" / "missing-desktop-extra.txt").read_text(
        encoding="utf-8"
    )


@pytest.fixture
def editor_bridge(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[SceneStore, asyncio.Queue[dict[str, typ.Any]]]:
    """Provide a shared editor registry and its observable snapshot stream."""
    shared = SceneStore()
    snapshots: asyncio.Queue[dict[str, typ.Any]] = asyncio.Queue()

    async def publish(payload: dict[str, typ.Any]) -> None:
        """Capture each post-edit publication in delivery order."""
        await snapshots.put(payload)

    monkeypatch.setattr(bridge, "store", shared)
    monkeypatch.setattr(bridge, "_async_broadcast", publish)
    return shared, snapshots


@pytest.fixture
def mcp_invocations(monkeypatch: pytest.MonkeyPatch) -> tuple[list[str], list[str]]:
    """Record launcher order and transport through the real main entry point."""
    calls: list[str] = []
    transports: list[str] = []

    def record_run(**kwargs: str) -> None:
        """Record stdio startup at the server boundary."""
        calls.append("run")
        transports.append(kwargs["transport"])

    monkeypatch.setattr(server, "_ensure_bridge", lambda: calls.append("bridge"))
    monkeypatch.setattr(server.mcp, "run", record_run)
    return calls, transports
