"""One named, visible or hidden voxel layer."""

from __future__ import annotations

import dataclasses


@dataclasses.dataclass(slots=True)
class VoxelLayer:
    """One named, optionally hidden layer of voxels."""

    name: str
    visible: bool = True
    # (x, y, z) -> color index key or RGB tuple stored as "#RRGGBB"
    blocks: dict[tuple[int, int, int], str] = dataclasses.field(default_factory=dict)

    def block_count(self) -> int:
        """
        Return the number of voxels held by this layer.

        Returns
        -------
        int
            Count of coordinates currently occupied in this layer.
        """
        return len(self.blocks)
