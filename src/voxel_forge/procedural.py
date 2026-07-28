"""Procedural voxel models with adjustable resolution."""

from __future__ import annotations

import math

from .model import VoxelScene


def build_tree(name: str = "tree", resolution: int = 4) -> VoxelScene:
    """
    Build an organic tree. Higher resolution = smaller voxels, more detail.
    resolution 1 = coarse (229 voxels), 4 = fine (~3000+), 8 = ultra (~15000+)
    """
    r = max(1, min(8, int(resolution)))
    vs = 1.0 / r
    scene = VoxelScene(name=name)
    scene.voxel_size = vs

    scene.set_palette_color("T", 101, 67, 33)
    scene.set_palette_color("B", 72, 48, 24)
    scene.set_palette_color("G", 55, 115, 38)
    scene.set_palette_color("R", 45, 95, 32)
    scene.set_palette_color("L", 46, 150, 46)
    scene.set_palette_color("D", 22, 105, 28)
    scene.set_palette_color("H", 72, 175, 58)

    def in_trunk(x: int, y: int, z: int) -> bool:
        if y < r or y >= 7 * r:
            return False
        taper = 1.0 - (y - r) / (6 * r) * 0.38
        rx = max(1, int(1.55 * r * taper))
        rz = max(1, int(1.55 * r * taper))
        return (x / (rx + 0.01)) ** 2 + (z / (rz + 0.01)) ** 2 <= 1.0

    grass_r = int(3.6 * r)
    for x in range(-grass_r, grass_r + 1):
        for z in range(-grass_r, grass_r + 1):
            d = math.hypot(x, z)
            if d <= grass_r + 0.3:
                if d >= grass_r - max(1, r // 2) and (x + z + x * z) % 3 == 0:
                    scene.place(x, 0, z, "R")
                else:
                    scene.place(x, 0, z, "G")

    for y in range(r, 7 * r):
        taper = 1.0 - (y - r) / (6 * r) * 0.38
        rx = max(1, int(1.55 * r * taper))
        rz = max(1, int(1.55 * r * taper))
        for x in range(-rx, rx + 1):
            for z in range(-rz, rz + 1):
                if (x / (rx + 0.01)) ** 2 + (z / (rz + 0.01)) ** 2 <= 1.0:
                    bark = "B" if (x * 3 + y * 5 + z * 7) % 11 == 0 else "T"
                    scene.place(x, y, z, bark)

    for angle in range(0, 360, 90):
        rad = math.radians(angle)
        dx, dz = math.cos(rad), math.sin(rad)
        for step in range(1, 3 * r):
            bx = int(round(dx * step * 0.55))
            bz = int(round(dz * step * 0.55))
            by = 5 * r + step // 2
            if not in_trunk(bx, by, bz):
                scene.place(bx, by, bz, "T")
            if step % 2 == 0 and not in_trunk(bx, by + 1, bz):
                scene.place(bx, by + 1, bz, "T")

    cy = 7 * r
    radius = 3.6 * r
    leaf_keys = ("L", "D", "H")
    span = int(radius) + r + 1

    for x in range(-span, span + 1):
        for y in range(4 * r, 12 * r):
            for z in range(-span, span + 1):
                dx = x - 0.4 * r
                dy = (y - cy) * 0.82
                dz = z - 0.4 * r
                dist_main = math.sqrt(dx * dx + dy * dy + dz * dz)

                dx2 = x - 2.2 * r
                dist_side = math.sqrt(dx2 * dx2 + dy * dy + dz * dz)
                dist = min(dist_main, dist_side * 1.05)

                noise = math.sin(x * 0.43 + y * 0.11) * math.cos(z * 0.39 + y * 0.07) * math.sin(y * 0.31) * r * 0.65

                if dist + noise > radius:
                    continue
                if in_trunk(x, y, z):
                    continue
                if dist > radius - r * 0.55 and noise < -0.35:
                    continue

                pick = leaf_keys[(x * 5 + y * 3 + z * 7) % 3]
                scene.place(x, y, z, pick)

    return scene


def build_chibi_bear(name: str = "chibi_bear", resolution: int = 3) -> VoxelScene:
    """รูปปั้นหมี chibi — หัวใหญ่ ตัวกลม ยืนบนฐาน."""
    r = max(2, min(6, int(resolution)))
    vs = 1.0 / r
    scene = VoxelScene(name=name)
    scene.voxel_size = vs

    scene.set_palette_color("F", 160, 105, 55)  # fur
    scene.set_palette_color("D", 110, 70, 35)  # dark fur / outline
    scene.set_palette_color("L", 250, 230, 200)  # snout + belly
    scene.set_palette_color("K", 25, 25, 30)  # eyes + nose
    scene.set_palette_color("P", 255, 170, 185)  # inner ear
    scene.set_palette_color("S", 90, 60, 40)  # wooden base

    def ellipsoid(x: int, y: int, z: int, cx: float, cy: float, cz: float, rx: float, ry: float, rz: float) -> bool:
        dx = (x - cx) / rx
        dy = (y - cy) / ry
        dz = (z - cz) / rz
        return dx * dx + dy * dy + dz * dz <= 1.0

    span = 6 * r
    head_y = 9 * r
    body_y = 4 * r

    # wooden base
    scene.fill_box(-3 * r, 3 * r, 0, 0, -3 * r, 3 * r, "S")
    scene.fill_box(-2 * r, 2 * r, 1, 1, -2 * r, 2 * r, "D")

    for x in range(-span, span + 1):
        for y in range(2, 14 * r):
            for z in range(-span, span + 1):
                in_body = ellipsoid(x, y, z, 0, body_y, 0, 2.8 * r, 2.4 * r, 2.5 * r)
                in_head = ellipsoid(x, y, z, 0, head_y, 0, 3.6 * r, 3.2 * r, 3.4 * r)

                # stubby arms
                in_arm_l = ellipsoid(x, y, z, -3.2 * r, body_y + 0.5 * r, 0, 1.2 * r, 1.6 * r, 1.1 * r)
                in_arm_r = ellipsoid(x, y, z, 3.2 * r, body_y + 0.5 * r, 0, 1.2 * r, 1.6 * r, 1.1 * r)
                # stubby legs
                in_leg_l = ellipsoid(x, y, z, -1.3 * r, 2.2 * r, 0.3 * r, 1.1 * r, 1.5 * r, 1.2 * r)
                in_leg_r = ellipsoid(x, y, z, 1.3 * r, 2.2 * r, 0.3 * r, 1.1 * r, 1.5 * r, 1.2 * r)

                if not (in_body or in_head or in_arm_l or in_arm_r or in_leg_l or in_leg_r):
                    continue

                color = "F"
                if in_body and not in_head:
                    # belly patch
                    if abs(x) <= r and abs(z) <= 1.5 * r and y <= body_y + r:
                        color = "L"
                scene.place(x, y, z, color)

    # ears
    for ex, ez in [(-2.4 * r, -0.5 * r), (2.4 * r, -0.5 * r)]:
        for x in range(-span, span + 1):
            for y in range(10 * r, 13 * r):
                for z in range(-span, span + 1):
                    if ellipsoid(x, y, z, ex, head_y + 2.2 * r, ez, 1.3 * r, 1.1 * r, 1.2 * r):
                        inner = ellipsoid(x, y, z, ex, head_y + 2.0 * r, ez, 0.7 * r, 0.6 * r, 0.65 * r)
                        scene.place(x, y, z, "P" if inner else "D")

    # snout
    for x in range(-span, span + 1):
        for y in range(7 * r, 10 * r):
            for z in range(-span, span + 1):
                if ellipsoid(x, y, z, 0, head_y - 1.2 * r, 2.8 * r, 1.8 * r, 1.4 * r, 1.5 * r):
                    scene.place(x, y, z, "L")

    # eyes
    for ex, ez in [(-1.3 * r, 2.5 * r), (1.3 * r, 2.5 * r)]:
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                for dz in range(-1, 2):
                    if dx * dx + dy * dy + dz * dz <= 2:
                        scene.place(int(ex + dx), int(head_y + 0.8 * r + dy), int(ez + dz), "K")

    # nose
    for x in range(-1, 2):
        for y in range(-1, 2):
            for z in range(0, 3):
                scene.place(x, int(head_y - 0.5 * r + y), int(3.5 * r + z), "K")

    # mouth line (dark fur)
    for x in range(-1, 2):
        scene.place(x, int(head_y - 1.8 * r), int(3.2 * r), "D")

    return scene
