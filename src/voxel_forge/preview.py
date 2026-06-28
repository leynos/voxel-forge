"""ASCII preview for AI inspection (like Goxel layer view)."""

from __future__ import annotations

from .model import VoxelScene


def layer_slice(scene: VoxelScene, y: int, layer_index: int | None = None) -> str:
    layer = scene.layers[layer_index if layer_index is not None else scene.active_layer]
    if not layer.blocks:
        return f"(empty layer '{layer.name}' at Y={y})"

    at_y = {(x, z): c for (x, yy, z), c in layer.blocks.items() if yy == y}
    if not at_y:
        return f"(no blocks at Y={y} in '{layer.name}')"

    xs = [p[0] for p in at_y]
    zs = [p[1] for p in at_y]
    min_x, max_x = min(0, min(xs) - 1), max(xs) + 1
    min_z, max_z = max(0, min(zs) - 1), max(zs) + 1

    lines = [f"Layer '{layer.name}' Y={y} (X right, Z down):"]
    header = "    " + "".join(f"{x:2}" for x in range(min_x, max_x + 1))
    lines.append(header)
    for z in range(min_z, max_z + 1):
        row = f"z{z:2} "
        for x in range(min_x, max_x + 1):
            row += at_y.get((x, z), ".") + " "
        lines.append(row)
    return "\n".join(lines)


def summary(scene: VoxelScene) -> str:
    b = scene.bounds()
    parts = [
        f"Scene: {scene.name}",
        f"Blocks: {scene.block_count()}",
        f"Layers: {len(scene.layers)} (active: {scene.layers[scene.active_layer].name})",
    ]
    if b:
        parts.append(
            f"Bounds: X[{b['minX']}..{b['maxX']}] Y[{b['minY']}..{b['maxY']}] Z[{b['minZ']}..{b['maxZ']}]"
        )
    parts.append(f"Palette keys: {', '.join(sorted(scene.palette.keys()))}")

    ys: set[int] = set()
    for layer in scene.layers:
        ys.update(y for (_, y, _) in layer.blocks)
    for y in sorted(ys):
        parts.append("")
        parts.append(layer_slice(scene, y))

    return "\n".join(parts)
