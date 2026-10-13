"""Procedural voxel models with adjustable resolution."""

from __future__ import annotations

import math
import typing as typ

from .model import VoxelScene

if typ.TYPE_CHECKING:
    import collections.abc as cabc

_TREE_PALETTE = (
    ("T", (101, 67, 33)),  # trunk
    ("B", (72, 48, 24)),  # bark speckle
    ("G", (55, 115, 38)),  # grass
    ("R", (45, 95, 32)),  # grass edge
    ("L", (46, 150, 46)),  # leaves
    ("D", (22, 105, 28)),  # leaves, shaded
    ("H", (72, 175, 58)),  # leaves, highlight
)
_BEAR_PALETTE = (
    ("F", (160, 105, 55)),  # fur
    ("D", (110, 70, 35)),  # dark fur / outline
    ("L", (250, 230, 200)),  # snout + belly
    ("K", (25, 25, 30)),  # eyes + nose
    ("P", (255, 170, 185)),  # inner ear
    ("S", (90, 60, 40)),  # wooden base
)

_LEAF_KEYS = ("L", "D", "H")
_TRUNK_BASE_RADIUS = 1.55
_TRUNK_TAPER = 0.38
# Vertical and radial extents are multiples of the resolution step, so a tree
# keeps its proportions as the voxels get smaller.
_TRUNK_TOP = 7  # the trunk occupies heights r up to 7r
_GRASS_RADIUS = 3.6
_CANOPY_RADIUS = 3.6
_CANOPY_CENTRE = 7  # the canopy is centred on the top of the trunk
# Leaves on the canopy's outer shell are dropped where the noise field digs in,
# which breaks up the silhouette instead of leaving a smooth ball.
_LEAF_EDGE_NOISE_CUTOFF = -0.35
_EYE_BLOB_RADIUS_SQUARED = 2


def _voxel_range(
    x_span: int, y_range: tuple[int, int], z_span: int
) -> cabc.Iterator[tuple[int, int, int]]:
    """Yield every integer point of a box centred on the vertical axis."""
    for x in range(-x_span, x_span + 1):
        for y in range(*y_range):
            for z in range(-z_span, z_span + 1):
                yield x, y, z


def _apply_palette(
    scene: VoxelScene, entries: tuple[tuple[str, tuple[int, int, int]], ...]
) -> None:
    """Register each ``(key, rgb)`` entry on the scene's palette."""
    for key, (red, green, blue) in entries:
        scene.set_palette_color(key, red, green, blue)


def _trunk_radius(y: int, r: int) -> int:
    """Return the trunk's half-width at height ``y``."""
    taper = 1.0 - (y - r) / (6 * r) * _TRUNK_TAPER
    return max(1, int(_TRUNK_BASE_RADIUS * r * taper))


def _in_trunk(x: int, y: int, z: int, r: int) -> bool:
    """Return whether a point falls inside the tapered trunk."""
    if y < r or y >= _TRUNK_TOP * r:
        return False
    radius = _trunk_radius(y, r)
    return (x / (radius + 0.01)) ** 2 + (z / (radius + 0.01)) ** 2 <= 1.0


def _place_grass(scene: VoxelScene, r: int) -> None:
    """Lay the grass disc the tree stands on."""
    grass_r = int(_GRASS_RADIUS * r)
    for x in range(-grass_r, grass_r + 1):
        for z in range(-grass_r, grass_r + 1):
            distance = math.hypot(x, z)
            if distance > grass_r + 0.3:
                continue
            rim = distance >= grass_r - max(1, r // 2)
            if rim and (x + z + x * z) % 3 == 0:
                scene.place(x, 0, z, "R")
            else:
                scene.place(x, 0, z, "G")


def _place_trunk(scene: VoxelScene, r: int) -> None:
    """Grow the trunk, speckled with darker bark."""
    for y in range(r, _TRUNK_TOP * r):
        radius = _trunk_radius(y, r)
        for x in range(-radius, radius + 1):
            for z in range(-radius, radius + 1):
                if (x / (radius + 0.01)) ** 2 + (z / (radius + 0.01)) ** 2 > 1.0:
                    continue
                bark = "B" if (x * 3 + y * 5 + z * 7) % 11 == 0 else "T"
                scene.place(x, y, z, bark)


def _place_branches(scene: VoxelScene, r: int) -> None:
    """Push four branches out of the upper trunk."""
    for angle in range(0, 360, 90):
        rad = math.radians(angle)
        dx, dz = math.cos(rad), math.sin(rad)
        for step in range(1, 3 * r):
            bx = round(dx * step * 0.55)
            bz = round(dz * step * 0.55)
            by = 5 * r + step // 2
            if not _in_trunk(bx, by, bz, r):
                scene.place(bx, by, bz, "T")
            if step % 2 == 0 and not _in_trunk(bx, by + 1, bz, r):
                scene.place(bx, by + 1, bz, "T")


def _canopy_distance(x: int, y: int, z: int, r: int) -> float:
    """Return the distance to the nearer of the canopy's two lobes."""
    dx = x - 0.4 * r
    dy = (y - _CANOPY_CENTRE * r) * 0.82
    dz = z - 0.4 * r
    dist_main = math.sqrt(dx * dx + dy * dy + dz * dz)
    dx_side = x - 2.2 * r
    dist_side = math.sqrt(dx_side * dx_side + dy * dy + dz * dz)
    return min(dist_main, dist_side * 1.05)


def _canopy_noise(x: int, y: int, z: int, r: int) -> float:
    """Return the displacement that roughens the canopy surface."""
    return (
        math.sin(x * 0.43 + y * 0.11)
        * math.cos(z * 0.39 + y * 0.07)
        * math.sin(y * 0.31)
        * r
        * 0.65
    )


def _place_canopy(scene: VoxelScene, r: int) -> None:
    """Fill the leafy canopy around and above the trunk."""
    radius = _CANOPY_RADIUS * r
    span = int(radius) + r + 1
    for x, y, z in _voxel_range(span, (4 * r, 12 * r), span):
        distance = _canopy_distance(x, y, z, r)
        noise = _canopy_noise(x, y, z, r)
        if distance + noise > radius or _in_trunk(x, y, z, r):
            continue
        if distance > radius - r * 0.55 and noise < _LEAF_EDGE_NOISE_CUTOFF:
            continue
        scene.place(x, y, z, _LEAF_KEYS[(x * 5 + y * 3 + z * 7) % 3])


def build_tree(name: str = "tree", resolution: int = 4) -> VoxelScene:
    """Build an organic tree.

    Parameters
    ----------
    name : str
        Name given to the generated scene.
    resolution : int
        Detail level, clamped to 1-8. Higher values mean smaller voxels and more
        of them: 1 is coarse (229 voxels), 4 is fine (~3000), 8 is ultra
        (~15000).

    Returns
    -------
    VoxelScene
        The generated tree.

    """
    r = max(1, min(8, int(resolution)))
    scene = VoxelScene(name=name)
    scene.voxel_size = 1.0 / r
    _apply_palette(scene, _TREE_PALETTE)
    _place_grass(scene, r)
    _place_trunk(scene, r)
    _place_branches(scene, r)
    _place_canopy(scene, r)
    return scene


def _in_ellipsoid(
    point: tuple[int, int, int],
    centre: tuple[float, float, float],
    radii: tuple[float, float, float],
) -> bool:
    """Return whether ``point`` lies inside an axis-aligned ellipsoid."""
    dx = (point[0] - centre[0]) / radii[0]
    dy = (point[1] - centre[1]) / radii[1]
    dz = (point[2] - centre[2]) / radii[2]
    return dx * dx + dy * dy + dz * dz <= 1.0


def _in_belly(point: tuple[int, int, int], r: int) -> bool:
    """Return whether a torso voxel sits on the bear's pale belly patch."""
    x, y, z = point
    centred = abs(x) <= r and abs(z) <= 1.5 * r
    return centred and y <= 4 * r + r


def _bear_body_colour(point: tuple[int, int, int], r: int) -> str | None:
    """Classify a bear voxel in priority order: head, belly/body, then limbs."""
    body_y = 4 * r
    if _in_ellipsoid(point, (0, 9 * r, 0), (3.6 * r, 3.2 * r, 3.4 * r)):
        return "F"
    if _in_ellipsoid(point, (0, body_y, 0), (2.8 * r, 2.4 * r, 2.5 * r)):
        return "L" if _in_belly(point, r) else "F"
    limbs = (
        ((-3.2 * r, body_y + 0.5 * r, 0), (1.2 * r, 1.6 * r, 1.1 * r)),
        ((3.2 * r, body_y + 0.5 * r, 0), (1.2 * r, 1.6 * r, 1.1 * r)),
        ((-1.3 * r, 2.2 * r, 0.3 * r), (1.1 * r, 1.5 * r, 1.2 * r)),
        ((1.3 * r, 2.2 * r, 0.3 * r), (1.1 * r, 1.5 * r, 1.2 * r)),
    )
    return (
        "F"
        if any(_in_ellipsoid(point, centre, radii) for centre, radii in limbs)
        else None
    )


def _place_bear_body(scene: VoxelScene, r: int, span: int) -> None:
    """Fill the bear's torso, head and stubby limbs."""
    coloured_points = (
        (*point, colour)
        for point in _voxel_range(span, (2, 14 * r), span)
        if (colour := _bear_body_colour(point, r)) is not None
    )
    for voxel in coloured_points:
        scene.place(*voxel)


def _place_bear_ear(
    scene: VoxelScene, r: int, span: int, centre_xz: tuple[float, float]
) -> None:
    """Add one ear, with its pink inner shell."""
    head_y = 9 * r
    outer_centre = (centre_xz[0], head_y + 2.2 * r, centre_xz[1])
    inner_centre = (centre_xz[0], head_y + 2.0 * r, centre_xz[1])
    for point in _voxel_range(span, (10 * r, 13 * r), span):
        if not _in_ellipsoid(point, outer_centre, (1.3 * r, 1.1 * r, 1.2 * r)):
            continue
        inner = _in_ellipsoid(point, inner_centre, (0.7 * r, 0.6 * r, 0.65 * r))
        scene.place(*point, "P" if inner else "D")


def _place_bear_snout(scene: VoxelScene, r: int, span: int) -> None:
    """Add the pale snout."""
    centre = (0.0, 9 * r - 1.2 * r, 2.8 * r)
    for point in _voxel_range(span, (7 * r, 10 * r), span):
        if _in_ellipsoid(point, centre, (1.8 * r, 1.4 * r, 1.5 * r)):
            scene.place(*point, "L")


def _place_bear_eyes(scene: VoxelScene, r: int) -> None:
    """Add both eyes as small solid blobs."""
    head_y = 9 * r
    for ex, ez in ((-1.3 * r, 2.5 * r), (1.3 * r, 2.5 * r)):
        for dx, dy, dz in _voxel_range(1, (-1, 2), 1):
            if dx * dx + dy * dy + dz * dz <= _EYE_BLOB_RADIUS_SQUARED:
                scene.place(int(ex + dx), int(head_y + 0.8 * r + dy), int(ez + dz), "K")


def _place_bear_face(scene: VoxelScene, r: int) -> None:
    """Add the nose block and the mouth line."""
    head_y = 9 * r
    for x in range(-1, 2):
        for y in range(-1, 2):
            for z in range(3):
                scene.place(x, int(head_y - 0.5 * r + y), int(3.5 * r + z), "K")
    for x in range(-1, 2):
        scene.place(x, int(head_y - 1.8 * r), int(3.2 * r), "D")


def build_chibi_bear(name: str = "chibi_bear", resolution: int = 3) -> VoxelScene:
    """รูปปั้นหมี chibi — หัวใหญ่ ตัวกลม ยืนบนฐาน.

    Parameters
    ----------
    name : str
        Name given to the generated scene.
    resolution : int
        Detail level, clamped to 2-6; higher values mean smaller voxels.

    Returns
    -------
    VoxelScene
        The generated statuette.

    """
    r = max(2, min(6, int(resolution)))
    scene = VoxelScene(name=name)
    scene.voxel_size = 1.0 / r
    _apply_palette(scene, _BEAR_PALETTE)

    span = 6 * r
    scene.fill_box(-3 * r, 3 * r, 0, 0, -3 * r, 3 * r, "S")
    scene.fill_box(-2 * r, 2 * r, 1, 1, -2 * r, 2 * r, "D")
    _place_bear_body(scene, r, span)
    for centre_xz in ((-2.4 * r, -0.5 * r), (2.4 * r, -0.5 * r)):
        _place_bear_ear(scene, r, span, centre_xz)
    _place_bear_snout(scene, r, span)
    _place_bear_eyes(scene, r)
    _place_bear_face(scene, r)
    return scene
