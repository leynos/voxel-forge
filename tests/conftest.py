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

from voxel_forge import bridge, server
from voxel_forge import scene_store as scene_store_module
from voxel_forge.model import SceneStore

# The scene the shared confirmation fixtures create. It is a single value the
# message-contract suites read back out of the strings they assert, so it lives
# here rather than being repeated as a literal in each module.
SCENE = "house"


@pytest.fixture
def scene_directory(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Point scene persistence at a temporary directory for one test."""
    directory = tmp_path / "scenes"
    directory.mkdir()
    monkeypatch.setattr(scene_store_module, "scenes_dir", lambda: directory)
    return directory


@pytest.fixture
def empty_server_store(monkeypatch: pytest.MonkeyPatch) -> SceneStore:
    """Replace the module-level scene registry and bridge sync for one test."""
    replacement = SceneStore()
    monkeypatch.setattr(server, "store", replacement)
    monkeypatch.setattr(server, "_sync_bridge", lambda _scene: None)
    return replacement


@pytest.fixture
def scene_store(empty_server_store: SceneStore) -> SceneStore:
    """Provide the server's store with one scene already created.

    Most confirmations only make sense once a scene exists, so the precondition
    lives here rather than as a ``create`` call repeated in every test. It
    builds on ``empty_server_store`` so the real store and bridge are still
    replaced for the duration of the test. This is shared rather than defined
    per module because the message-contract suites all read the same scene name
    back out of the confirmations they assert.
    """
    empty_server_store.create(SCENE)
    return empty_server_store


# The palette entry every shared confirmation fixture places and reads back.
# Named here because the fixtures below and the messages they assert on must
# agree on it, and a literal repeated three times cannot be changed safely.
SEED_COLOUR = "2"


def _seed(store: SceneStore, coordinate: tuple[int, int, int]) -> SceneStore:
    """Place the shared seed voxel at ``coordinate`` and return the store."""
    server.voxelforge_place_block(*coordinate, SEED_COLOUR)
    return store


@pytest.fixture
def occupied_store(scene_store: SceneStore) -> SceneStore:
    """Provide the scene store holding one voxel at the origin.

    Tests that act on existing geometry rather than creating it share this
    precondition, so the voxel is placed here instead of by a call repeated at
    the top of each.
    """
    return _seed(scene_store, (0, 0, 0))


@pytest.fixture
def adjacent_store(occupied_store: SceneStore) -> SceneStore:
    """Provide the scene store holding two voxels that share a face.

    Adjacency is the precondition the merge tests need: two voxels that merely
    exist would export as two parts however the merge were implemented, so the
    reduction the merged exports report is only observable when the geometry
    actually touches. Placing the neighbour here rather than at the top of each
    export test keeps that requirement stated once, and names the two voxels as
    the pair the merge is about rather than as two unrelated placements.
    """
    return _seed(occupied_store, (1, 0, 0))


def _data_file(name: str) -> str:
    """Return one file from ``tests/data`` as the exact text a test compares to."""
    return (Path(__file__).parent / "data" / name).read_text(encoding="utf-8")


@pytest.fixture
def about_message() -> str:
    """Return the exact text ``voxelforge_about`` is contracted to produce.

    The tool takes no arguments and reads no scene, so its response is fixed
    text and belongs in a data file rather than inline: the assertion stays
    readable, and a change to the project's self-description shows up as a
    one-line diff in ``tests/data`` instead of being hidden inside a block of
    concatenated string literals.
    """
    return _data_file("about-message.txt")


@pytest.fixture
def desktop_extra_hint() -> str:
    """Return complete user guidance shared by launcher and wheel checks."""
    return _data_file("missing-desktop-extra.txt")


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

    monkeypatch.setattr(
        server, "_ensure_bridge", lambda _trigger: calls.append("bridge")
    )
    monkeypatch.setattr(server.mcp, "run", record_run)
    return calls, transports
