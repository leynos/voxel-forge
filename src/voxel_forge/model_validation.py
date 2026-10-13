"""Pure scene-field validation, preserving the persisted ValueError contract."""

from __future__ import annotations

import typing as typ

if typ.TYPE_CHECKING:
    import collections.abc as cabc


import math

DEFAULT_PALETTE: dict[str, tuple[int, int, int]] = {
    "1": (255, 255, 255),
    "2": (255, 0, 0),
    "3": (0, 255, 0),
    "4": (0, 0, 255),
    "5": (255, 255, 0),
    "6": (255, 0, 255),
    "7": (0, 255, 255),
    "8": (128, 128, 128),
}

RGB_CHANNEL_COUNT = 3
MAX_CHANNEL = 255
FIRST_PRINTABLE_CODEPOINT = 32
HEX_COLOUR_LENGTH = 7
BLOCK_ROW_LENGTH = 4
MIN_SCENE_NAME_LENGTH = 1
MAX_SCENE_NAME_LENGTH = 80
MIN_VOXEL_SIZE = 0.05
MAX_VOXEL_SIZE = 2.0

_INVALID_SCENE_NAME_CHARS = frozenset('<>:"/\\|?*')
_WINDOWS_RESERVED_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{index}" for index in range(1, 10)}
    | {f"LPT{index}" for index in range(1, 10)}
)


class InvalidSceneDataError(ValueError):
    """Invalid serialized scene data; callers may continue catching ValueError.

    Used only at scene-schema boundaries, e.g. ``raise InvalidSceneDataError("name")``.
    """


def validate_scene_name(name: str) -> str:
    """Validate a scene name for use as a cross-platform filename component.

    Parameters
    ----------
    name : str
        Candidate scene name. The name is stored verbatim and must be a safe
        filename component on Windows, macOS, and Linux.

    Returns
    -------
    str
        The validated name, unchanged.

    Raises
    ------
    ValueError
        If ``name`` is not text, is empty, is longer than
        ``MAX_SCENE_NAME_LENGTH``, has leading or trailing whitespace, contains
        path separators, control characters, or other characters Windows
        forbids, or is a reserved Windows device name.
    """
    if not isinstance(name, str):
        msg = "scene name must be text"
        raise InvalidSceneDataError(msg)
    _reject_unsafe_scene_name(name)
    _reject_reserved_scene_name(name)
    return name


def _reject_unsafe_scene_name(name: str) -> None:
    """Reject scene names that are empty, over-long, or contain forbidden characters."""
    if not name or name != name.strip():
        msg = "scene name must contain 1 to 80 non-edge-whitespace characters"
        raise ValueError(msg)
    if len(name) > MAX_SCENE_NAME_LENGTH:
        msg = (
            "scene name must contain "
            f"{MIN_SCENE_NAME_LENGTH}"
            " to "
            f"{MAX_SCENE_NAME_LENGTH}"
            " non-edge-whitespace characters"
        )
        raise ValueError(msg)
    if name in {".", ".."} or any(
        character in _INVALID_SCENE_NAME_CHARS for character in name
    ):
        msg = "scene name cannot contain path or filename separators"
        raise ValueError(msg)
    if any(ord(character) < FIRST_PRINTABLE_CODEPOINT for character in name):
        msg = "scene name cannot contain control characters"
        raise ValueError(msg)


def _reject_reserved_scene_name(name: str) -> None:
    """Reject scene names Windows reserves, including device names with extensions."""
    stem = name.split(".", 1)[0].upper()
    if stem in _WINDOWS_RESERVED_NAMES or name.endswith((".", " ")):
        msg = "scene name is reserved by Windows"
        raise ValueError(msg)


def _validate_rgb(
    rgb: tuple[int, int, int] | list[int], *, field_name: str = "palette"
) -> tuple[int, int, int]:
    """Return three integer RGB channels in 0..255, rejecting booleans and other.

    non-integers.
    """
    if not isinstance(rgb, (list, tuple)) or len(rgb) != RGB_CHANNEL_COUNT:
        msg = f"{field_name} colours require three channels in the range 0..255"
        raise ValueError(msg)
    if any(
        type(channel) is not int or channel < 0 or channel > MAX_CHANNEL
        for channel in rgb
    ):
        msg = f"{field_name} colours require three integer channels in the range 0..255"
        raise ValueError(msg)
    return rgb[0], rgb[1], rgb[2]


def resolve_palette_colour(
    palette: cabc.Mapping[str, tuple[int, int, int]], color: str
) -> tuple[int, int, int]:
    """Resolve a palette key or ``#RRGGBB`` literal into 24-bit RGB.

    Parameters
    ----------
    palette : cabc.Mapping[str, tuple[int, int, int]]
        Palette mapping colour keys to RGB triples.
    color : str
        A palette key, or a ``#RRGGBB`` hexadecimal literal.

    Returns
    -------
    tuple[int, int, int]
        The resolved ``(r, g, b)`` triple.

    Raises
    ------
    ValueError
        If ``color`` is neither a palette key nor a well-formed ``#RRGGBB``
        literal.
    """
    if color in palette:
        return palette[color]
    if color.startswith("#") and len(color) == HEX_COLOUR_LENGTH:
        try:
            return (
                int(color[1:3], 16),
                int(color[3:5], 16),
                int(color[5:7], 16),
            )
        except ValueError as exc:
            msg = f"unknown colour '{color}'; use a palette key or #RRGGBB"
            raise ValueError(msg) from exc
    msg = f"unknown colour '{color}'; use a palette key or #RRGGBB"
    raise ValueError(msg)


def _validate_voxel_size(value: object) -> float:
    """Return the voxel size as a finite float inside the supported range."""
    voxel_size = float(value)
    if (
        not math.isfinite(voxel_size)
        or not MIN_VOXEL_SIZE <= voxel_size <= MAX_VOXEL_SIZE
    ):
        msg = (
            "voxel_size must be a finite number between "
            f"{MIN_VOXEL_SIZE}"
            " and "
            f"{MAX_VOXEL_SIZE}"
        )
        raise ValueError(msg)
    return voxel_size


def _require_text(value: object, field_name: str) -> str:
    """Return ``value`` when it is text, otherwise raise ``ValueError``."""
    if not isinstance(value, str):
        msg = f"{field_name} must be text"
        raise InvalidSceneDataError(msg)
    return value


def validate_layer_index(
    index: int, count: int, *, field_name: str = "layer_index"
) -> int:
    """Return a valid layer index, e.g. ``validate_layer_index(0, 1) == 0``.

    An out-of-range index raises ``ValueError`` naming ``field_name``. Reuse
    this validator for runtime scene edits and persisted active-layer fields.
    """
    if not 0 <= index < count:
        msg = f"{field_name} must be between 0 and {count - 1}"
        raise ValueError(msg)
    return index
