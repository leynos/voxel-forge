"""ASCII preview for AI inspection (like Goxel layer view)."""

from __future__ import annotations

import typing as typ

if typ.TYPE_CHECKING:
    from .model import VoxelScene


def _render_slice(occupancy: dict[tuple[int, int], str], header: str) -> str:
    """Return an ASCII grid for one X/Z occupancy map.

    The grid is padded by one cell on each side, and origin-clamped on the
    minimum edges so that the axes stay comparable between slices.
    """
    xs = [x for x, _ in occupancy]
    zs = [z for _, z in occupancy]
    min_x, max_x = min(0, min(xs) - 1), max(xs) + 1
    min_z, max_z = max(0, min(zs) - 1), max(zs) + 1

    lines = [header, "    " + "".join(f"{x:2}" for x in range(min_x, max_x + 1))]
    for z in range(min_z, max_z + 1):
        row = f"z{z:2} "
        for x in range(min_x, max_x + 1):
            row += occupancy.get((x, z), ".") + " "
        lines.append(row)
    return "\n".join(lines)


def layer_slice(scene: VoxelScene, y: int, layer_index: int | None = None) -> str:
    """Return an ASCII plan view of one layer at a single height.

    Parameters
    ----------
    scene
        Scene to inspect.
    y
        Height of the slice, in grid steps.
    layer_index
        Layer to slice; the active layer is used when omitted.

    Returns
    -------
    str
        Either the rendered grid, or a parenthesised note explaining why
        there is nothing to draw.
    """
    index = layer_index if layer_index is not None else scene.active_layer
    layer = scene.layers[index]
    if not layer.blocks:
        return f"(empty layer '{layer.name}' at Y={y})"

    at_y = {(x, z): c for (x, yy, z), c in layer.blocks.items() if yy == y}
    if not at_y:
        return f"(no blocks at Y={y} in '{layer.name}')"

    return _render_slice(at_y, f"Layer '{layer.name}' Y={y} (X right, Z down):")


def summary(scene: VoxelScene) -> str:
    """Return a multi-line digest of a scene for an AI reader.

    The digest reports totals, bounds, and palette keys, followed by an ASCII
    slice of the active layer for every height that holds voxels.
    """
    extent = scene.bounds()
    active_name = scene.layers[scene.active_layer].name
    parts = [
        f"Scene: {scene.name}",
        f"Blocks: {scene.block_count()}",
        f"Layers: {len(scene.layers)} (active: {active_name})",
    ]
    if extent:
        parts.append(
            f"Bounds: X[{extent['minX']}..{extent['maxX']}] "
            f"Y[{extent['minY']}..{extent['maxY']}] "
            f"Z[{extent['minZ']}..{extent['maxZ']}]"
        )
    parts.append(f"Palette keys: {', '.join(sorted(scene.palette.keys()))}")

    ys: set[int] = set()
    for layer in scene.layers:
        ys.update(y for (_, y, _) in layer.blocks)
    for y in sorted(ys):
        parts.extend(("", layer_slice(scene, y)))

    return "\n".join(parts)
