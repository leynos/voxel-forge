"""Validation helpers and limits for the voxel scene model.

Scenes arrive from untrusted JSON documents and from MCP tool arguments, so
every field is checked before it reaches a ``VoxelScene``. Values of the right
shape but the wrong content raise ``ValueError``; values of the wrong type
raise ``TypeError``.
"""

from __future__ import annotations

import math

MAX_SCENE_NAME_LENGTH = 80
FIRST_PRINTABLE_CODEPOINT = 32
RGB_CHANNEL_COUNT = 3
MIN_CHANNEL = 0
MAX_CHANNEL = 255
MIN_VOXEL_SIZE = 0.05
MAX_VOXEL_SIZE = 2.0
HEX_COLOUR_LENGTH = 7
BLOCK_ROW_LENGTH = 4

_INVALID_SCENE_NAME_CHARS = frozenset('<>:"/\\|?*')
_WINDOWS_RESERVED_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{index}" for index in range(1, 10)}
    | {f"LPT{index}" for index in range(1, 10)}
)
_RESERVED_TRAILING_CHARACTERS = (".", " ")


def _has_usable_length(name: str) -> bool:
    """Return whether the name is non-empty, trimmed, and short enough."""
    if not name or name != name.strip():
        return False
    return len(name) <= MAX_SCENE_NAME_LENGTH


def _is_separator_free(name: str) -> bool:
    """Return whether the name is free of path and filename separators."""
    if name in {".", ".."}:
        return False
    return not any(character in _INVALID_SCENE_NAME_CHARS for character in name)


def _is_windows_safe(name: str) -> bool:
    """Return whether Windows will accept the name as a filename stem."""
    if name.rstrip(". ").upper() in _WINDOWS_RESERVED_NAMES:
        return False
    return not name.endswith(_RESERVED_TRAILING_CHARACTERS)


def validate_scene_name(name: str) -> str:
    """Return a safe cross-platform scene filename component.

    Parameters
    ----------
    name
        Candidate scene name, used verbatim as the stem of a JSON file.

    Returns
    -------
    str
        The unchanged name, once it is known to be safe.

    Raises
    ------
    TypeError
        If the name is not text.
    ValueError
        If the name is empty or over-long, is padded with whitespace,
        contains path separators or control characters, or is reserved by
        Windows.

    Examples
    --------
    >>> validate_scene_name("house")
    'house'
    """
    if not isinstance(name, str):
        msg = "scene name must be text"
        raise TypeError(msg)
    if not _has_usable_length(name):
        msg = "scene name must contain 1 to 80 non-edge-whitespace characters"
        raise ValueError(msg)
    if not _is_separator_free(name):
        msg = "scene name cannot contain path or filename separators"
        raise ValueError(msg)
    if any(ord(character) < FIRST_PRINTABLE_CODEPOINT for character in name):
        msg = "scene name cannot contain control characters"
        raise ValueError(msg)
    if not _is_windows_safe(name):
        msg = "scene name is reserved by Windows"
        raise ValueError(msg)
    return name


def validate_rgb(
    rgb: tuple[int, int, int] | list[int], *, field_name: str = "palette"
) -> tuple[int, int, int]:
    """Return an RGB triple whose channels all lie in the range 0..255.

    Parameters
    ----------
    rgb
        Three integer-like channel values in red, green, blue order.
    field_name
        Name used to attribute the failure in the error message.

    Returns
    -------
    tuple of int
        The coerced channel values.

    Raises
    ------
    ValueError
        If the triple has the wrong length or an out-of-range channel.

    Examples
    --------
    >>> validate_rgb([0, 128, 255])
    (0, 128, 255)
    """
    channels = tuple(int(channel) for channel in rgb)
    if len(channels) != RGB_CHANNEL_COUNT or any(
        not MIN_CHANNEL <= channel <= MAX_CHANNEL for channel in channels
    ):
        msg = f"{field_name} colours require three channels in the range 0..255"
        raise ValueError(msg)
    return channels


def validate_voxel_size(voxel_size: float) -> float:
    """Return a finite world-unit voxel size within the supported range.

    Parameters
    ----------
    voxel_size
        World units per grid step; 0.25 gives four times the detail of 1.0.

    Returns
    -------
    float
        The unchanged voxel size, once it is known to be usable.

    Raises
    ------
    ValueError
        If the size is not finite or falls outside 0.05..2.0.

    Examples
    --------
    >>> validate_voxel_size(0.25)
    0.25
    """
    in_range = MIN_VOXEL_SIZE <= voxel_size <= MAX_VOXEL_SIZE
    if not math.isfinite(voxel_size) or not in_range:
        msg = "voxel_size must be a finite number between 0.05 and 2.0"
        raise ValueError(msg)
    return voxel_size
