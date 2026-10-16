"""Greedy box merging combines adjacent same-colour voxels into larger parts."""

from __future__ import annotations

import dataclasses
import operator
import typing as typ

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    from .model import VoxelScene


@dataclasses.dataclass(frozen=True, slots=True)
class MergedBox:
    """An axis-aligned run of same-coloured voxels, inclusive of both corners."""

    x1: int
    y1: int
    z1: int
    x2: int  # inclusive
    y2: int
    z2: int
    color: str

    @property
    def volume(self) -> int:
        """The number of voxels the box stands in for."""
        return (
            (self.x2 - self.x1 + 1) * (self.y2 - self.y1 + 1) * (self.z2 - self.z1 + 1)
        )


@dataclasses.dataclass(slots=True)
class _MergeState:
    """The voxel map plus the set of cells no box has claimed yet."""

    voxels: dict[tuple[int, int, int], str]
    remaining: set[tuple[int, int, int]]

    def matches(self, cell: tuple[int, int, int], colour: str) -> bool:
        """Return whether the cell is still unclaimed and of the given colour."""
        return cell in self.remaining and self.voxels[cell] == colour

    def slab_matches(
        self, cells: cabc.Iterable[tuple[int, int, int]], colour: str
    ) -> bool:
        """Return whether every cell of a candidate slab matches the colour."""
        return all(self.matches(cell, colour) for cell in cells)

    def claim(self, box: MergedBox) -> None:
        """Remove every cell inside the box from the unclaimed set."""
        self.remaining.difference_update(
            (xi, yi, zi)
            for xi in range(box.x1, box.x2 + 1)
            for yi in range(box.y1, box.y2 + 1)
            for zi in range(box.z1, box.z2 + 1)
        )


def _grow_box(state: _MergeState, seed: tuple[int, int, int]) -> MergedBox:
    """Return the largest single-colour box anchored at the seed cell.

    The box grows along X first, then Z, then Y, taking each axis as far as a
    whole slab of unclaimed voxels shares the seed colour.
    """
    colour = state.voxels[seed]
    x0, y0, z0 = seed
    max_x, max_y, max_z = x0, y0, z0

    while state.matches((max_x + 1, y0, z0), colour):
        max_x += 1

    while state.slab_matches(
        ((xi, y0, max_z + 1) for xi in range(x0, max_x + 1)), colour
    ):
        max_z += 1

    while state.slab_matches(
        (
            (xi, max_y + 1, zi)
            for xi in range(x0, max_x + 1)
            for zi in range(z0, max_z + 1)
        ),
        colour,
    ):
        max_y += 1

    return MergedBox(x0, y0, z0, max_x, max_y, max_z, colour)


def collect_voxels(scene: VoxelScene) -> dict[tuple[int, int, int], str]:
    """Collect every visible layer, letting later (upper) layers win overlaps."""
    voxels: dict[tuple[int, int, int], str] = {}
    for layer in scene.layers:
        if not layer.visible:
            continue
        voxels.update(dict(layer.blocks.items()))
    return voxels


def merge_boxes(voxels: dict[tuple[int, int, int], str]) -> list[MergedBox]:
    """Merge neighbouring same-coloured voxels into as few boxes as possible.

    Greedy merge: grow each box from a corner (min Y, Z, X) as far as
    same-coloured neighbours allow. On many models this reduces tens of
    thousands of voxels to a few hundred parts.
    """
    state = _MergeState(voxels=voxels, remaining=set(voxels.keys()))
    boxes: list[MergedBox] = []

    while state.remaining:
        seed = min(state.remaining, key=operator.itemgetter(1, 2, 0))
        box = _grow_box(state, seed)
        state.claim(box)
        boxes.append(box)

    return boxes


def merge_scene(scene: VoxelScene) -> list[MergedBox]:
    """Return the merged boxes for every visible layer of a scene."""
    return merge_boxes(collect_voxels(scene))


def merge_stats(scene: VoxelScene) -> dict[str, int | float]:
    """Return how much the greedy merge reduces the exported part count."""
    voxels = collect_voxels(scene)
    boxes = merge_boxes(dict(voxels))
    raw = len(voxels)
    merged = len(boxes)
    saved = raw - merged if raw else 0
    ratio = (saved / raw * 100) if raw else 0.0
    return {
        "voxels": raw,
        "merged_boxes": merged,
        "parts_saved": saved,
        "reduction_percent": round(ratio, 1),
    }
