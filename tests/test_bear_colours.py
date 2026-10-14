"""Bear geometry priorities at body, head, limb, and empty-space boundaries."""

from __future__ import annotations

import pytest

from voxel_forge.procedural import _bear_body_colour


@pytest.mark.parametrize(
    ("point", "expected"),
    [
        ((0, 12, 0), "F"),
        ((0, 8, 2), "L"),
        ((6, 9, 0), "F"),
        ((0, 18, 0), "F"),
        ((12, 28, 12), None),
    ],
    ids=["head-over-body", "belly", "arm", "head", "empty-space"],
)
def test_bear_regions_keep_colour_priority(
    point: tuple[int, int, int], expected: str | None
) -> None:
    """Head overlaps keep fur colour, belly stays light, and empty space is skipped."""
    assert _bear_body_colour(point, 2) == expected, "region precedence must stay intact"
