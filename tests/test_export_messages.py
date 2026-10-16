"""Executable contract for the messages the import and export tools return.

Roadmap task 1.4.2 translated these confirmations from Thai into English. Two
of them name a quantity that is otherwise unrecoverable from the call: the
Roblox export reports a reduction percentage, and the VOX import reports the
resulting scene's voxel count. A caller who reads only the words "export
Roblox merged" cannot tell a complete export from one that merged nothing.

The exported *file contents* are not asserted here -- they are covered by the
format tests elsewhere. These tests pin what the tool says it did, and where
it says it wrote to, which is the part a caller acts on.

Run with ``uv run pytest -q``. Both the destination paths and the scene store
are redirected at temporary directories, so nothing here reads or writes a
real ``~/.voxel-forge`` directory.
"""

from __future__ import annotations

import typing as typ

from voxel_forge import server

if typ.TYPE_CHECKING:
    from pathlib import Path

    from voxel_forge.model import SceneStore

# Matches the scene ``conftest.py``'s ``scene_store`` fixture creates.
_SCENE = "house"


def test_import_confirmation_reports_the_scene_and_voxel_count(
    adjacent_store: SceneStore, tmp_path: Path
) -> None:
    """An import must report the scene it produced and how many voxels it holds.

    The count is what tells a caller the file was read completely rather than
    partially; the scene name is derived from the filename, so reporting it
    lets the caller address the new scene without guessing at that derivation.

    The source is a VOX file this test exports first, so the assertion covers a
    real round trip rather than a hand-built file that might not resemble what
    the exporter writes. Singular and plural are both "voxels" in this message,
    which is why a count of 2 is used: the string is compared in full, so a
    formatter that started pluralizing would fail here rather than silently
    changing caller-visible text.
    """
    source = tmp_path / "source.vox"
    server.voxelforge_export_vox(_SCENE, str(source))

    imported = server.voxelforge_import_vox(str(source))

    assert imported == f"import '{source}' → scene 'source' (2 voxels)", (
        "the import must name the file read, the scene produced, and its size"
    )
    assert server.store.get("source").block_count() == 2, (
        "the reported count must match the scene that was actually registered"
    )


def test_roblox_export_confirmation_reports_the_reduction(
    adjacent_store: SceneStore, tmp_path: Path
) -> None:
    """A Roblox export must report the part count and the reduction it achieved.

    The reduction is the whole point of the merged export: a caller choosing
    between this tool and a per-voxel export needs to know how much geometry
    the merge actually removed. Two adjacent voxels merging into one Part is a
    50% reduction, which is a figure a broken merge cannot produce -- reporting
    zero would fail here rather than looking plausible.

    The trailing line names the Roblox Studio tool the caller runs the result
    with, so it is pinned too: it is the only place the export says what to do
    with the file.
    """
    destination = tmp_path / "scene.luau"

    assert server.voxelforge_export_roblox_merged(_SCENE, str(destination)) == (
        f"export Roblox merged -> {destination}\n"
        "  2 voxels -> 1 Parts (50.0% reduction)\n"
        "  run it in Studio with execute_luau"
    ), "the Roblox export must report its part count, reduction, and next step"
    assert destination.read_text(encoding="utf-8"), (
        "the confirmation must describe a file that was actually written"
    )


def test_legacy_obj_export_confirmation_says_it_did_not_merge(
    adjacent_store: SceneStore, tmp_path: Path
) -> None:
    """The unmerged OBJ export must say so, to distinguish it from the merged one.

    ``export_obj`` and ``export_obj_legacy`` write different files for the same
    scene, and this tool's response is where a caller learns which one they
    got. The phrase "no merge" is the only signal in the message; without it
    the two confirmations would differ only by path.
    """
    destination = tmp_path / "legacy.obj"

    assert server.voxelforge_export_obj_legacy(_SCENE, str(destination)) == (
        f"export .obj (no merge) -> {destination} (2 voxels)"
    ), "the legacy export must say it did not merge, and report the voxel count"
