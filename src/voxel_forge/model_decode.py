"""Decode persisted palettes and layers without filesystem access."""

from __future__ import annotations

import typing as typ

if typ.TYPE_CHECKING:
    import collections.abc as cabc


from .model_layer import VoxelLayer
from .model_validation import (
    BLOCK_ROW_LENGTH,
    DEFAULT_PALETTE,
    RGB_CHANNEL_COUNT,
    InvalidSceneDataError,
    _require_int,
    _require_text,
    _validate_rgb,
    resolve_palette_colour,
)


def _parse_palette(raw: object) -> dict[str, tuple[int, int, int]]:
    """Return the default palette with any scene-supplied overrides applied."""
    palette = dict(DEFAULT_PALETTE)
    if raw is None:
        return palette
    if not isinstance(raw, dict):
        msg = "palette must be a JSON object"
        raise InvalidSceneDataError(msg)
    for key, value in raw.items():
        if not isinstance(value, (list, tuple)) or len(value) != RGB_CHANNEL_COUNT:
            msg = f"palette colour {key!r} must contain three channels"
            raise InvalidSceneDataError(msg)
        palette[str(key)] = _validate_rgb(value)
    return palette


def _parse_block(
    row: object, palette: cabc.Mapping[str, tuple[int, int, int]]
) -> tuple[tuple[int, int, int], str]:
    """Return the coordinate and validated colour of one serialised block row."""
    if not isinstance(row, (list, tuple)) or len(row) != BLOCK_ROW_LENGTH:
        msg = "each block must be [x, y, z, colour]"
        raise InvalidSceneDataError(msg)
    colour = _require_text(row[3], "block colour")
    resolve_palette_colour(palette, colour)
    coordinate = (
        _require_int(row[0], "block coordinate x"),
        _require_int(row[1], "block coordinate y"),
        _require_int(row[2], "block coordinate z"),
    )
    return coordinate, colour


def _parse_layer(
    raw: object, palette: cabc.Mapping[str, tuple[int, int, int]]
) -> VoxelLayer:
    """Build one layer, validating its schema boundary and every block row."""
    if not isinstance(raw, dict):
        msg = "each layer must be a JSON object"
        raise InvalidSceneDataError(msg)
    visible = raw.get("visible", True)
    if not isinstance(visible, bool):
        msg = "layer visible must be a boolean"
        raise InvalidSceneDataError(msg)
    layer = VoxelLayer(
        name=_require_text(raw.get("name", "Layer"), "layer name"),
        visible=visible,
    )
    blocks = raw.get("blocks", [])
    if not isinstance(blocks, list):
        msg = "layer blocks must be a JSON array"
        raise InvalidSceneDataError(msg)
    for row in blocks:
        coordinate, colour = _parse_block(row, palette)
        layer.blocks[coordinate] = colour
    return layer


def _parse_layers(
    raw: object, palette: cabc.Mapping[str, tuple[int, int, int]]
) -> list[VoxelLayer]:
    """Build every layer described by a serialised scene."""
    if not isinstance(raw, list):
        msg = "layers must be a JSON array"
        raise InvalidSceneDataError(msg)
    return [_parse_layer(entry, palette) for entry in raw]
