"""Check that persisted scene fields preserve their JSON schema types."""

import pytest

from voxel_forge.model import VoxelScene
from voxel_forge.model_validation import InvalidSceneDataError


@pytest.mark.parametrize("axis", range(3), ids=["x", "y", "z"])
@pytest.mark.parametrize(
    "value", [None, 1.9, True, "3"], ids=["null", "fraction", "boolean", "text"]
)
def test_block_coordinates_require_integers(axis: int, value: object) -> None:
    """Each coordinate rejects missing values and coercible non-integers."""
    data = VoxelScene("valid").to_dict()
    row: list[object] = [0, 0, 0, "1"]
    row[axis] = value
    data["layers"][0]["blocks"] = [row]

    with pytest.raises(InvalidSceneDataError, match="block coordinate"):
        VoxelScene.from_dict(data)


@pytest.mark.parametrize(
    "value", [None, 3, True, ["3"]], ids=["null", "integer", "boolean", "array"]
)
def test_block_colour_requires_text(value: object) -> None:
    """A numeric palette key cannot make a numeric block colour valid."""
    data = VoxelScene("valid").to_dict()
    data["palette"]["3"] = [255, 0, 0]
    data["layers"][0]["blocks"] = [[0, 0, 0, value]]

    with pytest.raises(InvalidSceneDataError, match="block colour"):
        VoxelScene.from_dict(data)


_FIELD_CASES = [
    ("active_layer", "active_layer", (None, 1.9, True, "3")),
    ("name", "scene name", (None, ["a"], {"a": 1}, 7)),
    ("layer_name", "layer name", (None, 3, True, ["Layer"])),
    ("layer_visible", "layer visible", (None, 0, "false", [])),
]


@pytest.mark.parametrize(
    ("field", "message", "value"),
    [
        pytest.param(field, message, value, id=f"{field}-{index}")
        for field, message, values in _FIELD_CASES
        for index, value in enumerate(values)
    ],
)
def test_scene_fields_require_declared_types(
    field: str, message: str, value: object
) -> None:
    """Each schema field rejects coercible values through the domain error."""
    data = VoxelScene("valid").to_dict()
    if field.startswith("layer_"):
        target = data["layers"][0]
        key = field.removeprefix("layer_")
    else:
        target = data
        key = field
    target[key] = value

    with pytest.raises(InvalidSceneDataError, match=message):
        VoxelScene.from_dict(data)


@pytest.mark.parametrize("visible", [False, True], ids=["hidden", "visible"])
def test_valid_scene_types_round_trip(*, visible: bool) -> None:
    """Strict decoding preserves integer coordinates and both boolean states."""
    data = VoxelScene("valid").to_dict()
    data["palette"]["3"] = [255, 0, 0]
    data["layers"][0].update(name="Layer", visible=visible, blocks=[[-3, 0, 3, "3"]])

    assert VoxelScene.from_dict(data).to_dict() == data, (
        "valid wire types must round-trip without changing the scene"
    )
