"""Scene-count and MCP edit-publication contracts."""

from __future__ import annotations

import typing as typ
from unittest import mock

import pytest

from voxel_forge import server
from voxel_forge.model import SceneStore, VoxelScene

if typ.TYPE_CHECKING:
    import collections.abc as cabc


def test_scene_count_includes_hidden_layer_records() -> None:
    """The count must include each layer even when rendering hides its voxels."""
    scene = VoxelScene("layers")
    scene.place(0, 0, 0)
    hidden = scene.add_layer("hidden")
    hidden.visible = False
    scene.place(1, 0, 0, layer_index=1)

    assert hidden.block_count() == 1, "the hidden layer must retain its voxel"
    assert scene.block_count() == 2, "both layer records must contribute to the count"
    assert len(scene.all_blocks()) == 1, "visibility must affect rendering, not counts"


@pytest.mark.parametrize("operation", ["palette", "place"])
@pytest.mark.parametrize("is_valid", [True, False])
def test_mcp_edits_publish_only_after_success(
    monkeypatch: pytest.MonkeyPatch, operation: str, *, is_valid: bool
) -> None:
    """Palette and voxel edits must publish once on success and never on failure."""
    store = SceneStore()
    scene = store.create("editing")
    monkeypatch.setattr(server, "store", store)
    publish = mock.Mock()
    monkeypatch.setattr(server, "_sync_bridge", publish)
    callbacks: dict[str, cabc.Callable[[], str]] = {
        "palette": lambda: server.voxelforge_set_palette(
            "new", 0, 0, 0 if is_valid else -1
        ),
        "place": lambda: server.voxelforge_place_block(
            0, 0, 0, "1" if is_valid else "missing"
        ),
    }

    if is_valid:
        callbacks[operation]()
        publish.assert_called_once_with(scene)
    else:
        with pytest.raises(ValueError, match="colour"):
            callbacks[operation]()
        publish.assert_not_called()
        assert scene.block_count() == 0, "a rejected edit must not add a voxel"
        assert "new" not in scene.palette, "a rejected edit must not add a colour"
