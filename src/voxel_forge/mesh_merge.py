"""Greedy box merging — รวม voxel สีเดียวกันที่ติดกันเป็นกล่องใหญ่ ลด mesh/part ตอน export."""

from __future__ import annotations

from dataclasses import dataclass

from .model import VoxelScene


@dataclass(frozen=True)
class MergedBox:
    x1: int
    y1: int
    z1: int
    x2: int  # inclusive
    y2: int
    z2: int
    color: str

    @property
    def volume(self) -> int:
        return (self.x2 - self.x1 + 1) * (self.y2 - self.y1 + 1) * (self.z2 - self.z1 + 1)


def collect_voxels(scene: VoxelScene) -> dict[tuple[int, int, int], str]:
    """รวมทุก layer ที่มองเห็น — ถ้าทับกันใช้ layer หลัง (ด้านบน)."""
    voxels: dict[tuple[int, int, int], str] = {}
    for layer in scene.layers:
        if not layer.visible:
            continue
        for pos, color in layer.blocks.items():
            voxels[pos] = color
    return voxels


def merge_boxes(voxels: dict[tuple[int, int, int], str]) -> list[MergedBox]:
    """
    Greedy merge: ขยายกล่องจากมุม (min Y, Z, X) ให้ใหญ่สุดเท่าที่สีเดียวกันและติดกัน
    ลด 17k voxels เหลือหลักร้อย part ได้ในหลายโมเดล
    """
    remaining = set(voxels.keys())
    boxes: list[MergedBox] = []

    while remaining:
        seed = min(remaining, key=lambda p: (p[1], p[2], p[0]))
        color = voxels[seed]
        x0, y0, z0 = seed

        max_x = x0
        while (max_x + 1, y0, z0) in remaining and voxels[(max_x + 1, y0, z0)] == color:
            max_x += 1

        max_z = z0
        while True:
            ok = all(
                (xi, y0, max_z + 1) in remaining and voxels[(xi, y0, max_z + 1)] == color
                for xi in range(x0, max_x + 1)
            )
            if not ok:
                break
            max_z += 1

        max_y = y0
        while True:
            ok = all(
                (xi, max_y + 1, zi) in remaining and voxels[(xi, max_y + 1, zi)] == color
                for xi in range(x0, max_x + 1)
                for zi in range(z0, max_z + 1)
            )
            if not ok:
                break
            max_y += 1

        for xi in range(x0, max_x + 1):
            for yi in range(y0, max_y + 1):
                for zi in range(z0, max_z + 1):
                    remaining.discard((xi, yi, zi))

        boxes.append(MergedBox(x0, y0, z0, max_x, max_y, max_z, color))

    return boxes


def merge_scene(scene: VoxelScene) -> list[MergedBox]:
    return merge_boxes(collect_voxels(scene))


def merge_stats(scene: VoxelScene) -> dict[str, int | float]:
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
