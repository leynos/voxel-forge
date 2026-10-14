"""Export สำหรับ Roblox — รวม voxel เป็น Part ใหญ่ (group ใน Model)."""

from __future__ import annotations

import typing as typ

from .mesh_merge import merge_scene
from .paths import exports_dir

if typ.TYPE_CHECKING:
    from pathlib import Path

    from .model import VoxelScene


def to_luau_merged(
    scene: VoxelScene,
    *,
    parent: str = "workspace",
    anchor: bool = True,
) -> str:
    """Return a Luau script that rebuilds the scene from merged parts.

    สร้าง Luau ที่ใช้ Part ใหญ่แทน 1 voxel = 1 Part (ลด lag).

    Parameters
    ----------
    scene : VoxelScene
        Scene to export.
    parent : str, optional
        Luau expression the generated ``Model`` is parented to. Defaults to
        ``"workspace"``.
    anchor : bool, optional
        Whether every generated part is anchored. Defaults to ``True``.

    Returns
    -------
    str
        Generated Luau source code.

    Examples
    --------
    The default parent appears in the generated script::

        >>> from voxel_forge.export_roblox import to_luau_merged
        >>> from voxel_forge.model import VoxelScene
        >>> scene = VoxelScene("example")
        >>> "model.Parent = workspace" in to_luau_merged(scene)
        True
    """
    vs = scene.voxel_size
    boxes = merge_scene(scene)
    stats_voxels = sum(b.volume for b in boxes)

    palette_lines = "\n".join(
        f'\t["{k}"] = Color3.fromRGB({r}, {g}, {b}),'
        for k, (r, g, b) in sorted(scene.palette.items())
    )

    box_lines = ",\n".join(
        f'\t{{ {b.x1}, {b.y1}, {b.z1}, {b.x2}, {b.y2}, {b.z2}, "{b.color}" }}'
        for b in sorted(boxes, key=lambda b: (b.y1, b.z1, b.x1))
    )

    return f"""-- VoxelForge merged export — {scene.name}
-- voxels: {stats_voxels} -> parts: {len(boxes)} (merged)

local VOXEL = {vs}
local PALETTE = {{
{palette_lines}
}}

local BOXES = {{
{box_lines}
}}

local model = Instance.new("Model")
model.Name = "{scene.name}"

for i, spec in ipairs(BOXES) do
\tlocal x1, y1, z1, x2, y2, z2, colorKey = table.unpack(spec)
\tlocal sx = (x2 - x1 + 1) * VOXEL
\tlocal sy = (y2 - y1 + 1) * VOXEL
\tlocal sz = (z2 - z1 + 1) * VOXEL
\tlocal cx = (x1 + x2 + 1) * 0.5 * VOXEL
\tlocal cy = (y1 + y2 + 1) * 0.5 * VOXEL
\tlocal cz = (z1 + z2 + 1) * 0.5 * VOXEL

\tlocal part = Instance.new("Part")
\tpart.Name = string.format("Merged_%d", i)
\tpart.Size = Vector3.new(sx, sy, sz)
\tpart.Material = Enum.Material.SmoothPlastic
\tpart.Color = PALETTE[colorKey] or Color3.fromRGB(255, 255, 255)
\tpart.Anchored = {str(anchor).lower()}
\tpart.Orientation = Vector3.zero
\tpart.Position = Vector3.new(cx, cy, cz)
\tpart.Parent = model
end

model.Parent = {parent}
return model
"""


def write_luau_file(scene: VoxelScene, directory: Path | None = None) -> Path:
    """Write the merged Luau export to ``directory`` and return its path.

    The default destination is ``~/.voxel-forge/exports``, created on demand.

    Parameters
    ----------
    scene : VoxelScene
        Scene to export.
    directory : Path | None, optional
        Destination directory. When omitted, use ``exports_dir()``; defaults
        to ``None``.

    Returns
    -------
    Path
        Path to the written ``.server.luau`` file.

    Raises
    ------
    OSError
        If the destination directory cannot be created or the file cannot be
        written. Errors from the default ``exports_dir()`` destination also
        propagate.

    Examples
    --------
    Write into a temporary directory and check the returned filename::

        >>> from pathlib import Path
        >>> from tempfile import TemporaryDirectory
        >>> from voxel_forge.export_roblox import write_luau_file
        >>> from voxel_forge.model import VoxelScene
        >>> scene = VoxelScene("example")
        >>> with TemporaryDirectory() as temporary_directory:
        ...     output = write_luau_file(scene, Path(temporary_directory))
        ...     output.name
        'example_merged.server.luau'
    """
    directory = directory or exports_dir()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{scene.name}_merged.server.luau"
    path.write_text(to_luau_merged(scene), encoding="utf-8")
    return path
