"""Core voxel scene model — layers, 24-bit RGB, Goxel/MagicaVoxel compatible grid."""

from __future__ import annotations

import dataclasses
import json
import typing as typ
from pathlib import Path

from voxel_forge.model_validation import (
    BLOCK_ROW_LENGTH,
    HEX_COLOUR_LENGTH,
    RGB_CHANNEL_COUNT,
    validate_rgb,
    validate_scene_name,
    validate_voxel_size,
)

DEFAULT_PALETTE: dict[str, tuple[int, int, int]] = {
    "1": (255, 255, 255),
    "2": (255, 0, 0),
    "3": (0, 255, 0),
    "4": (0, 0, 255),
    "5": (255, 255, 0),
    "6": (255, 0, 255),
    "7": (0, 255, 255),
    "8": (128, 128, 128),
}


def _data_dir() -> Path:
    """Return the scene directory, creating it if it does not yet exist."""
    root = Path.home() / ".voxel-forge" / "scenes"
    root.mkdir(parents=True, exist_ok=True)
    return root


@dataclasses.dataclass
class VoxelLayer:
    """One named, independently hideable layer of coloured voxels."""

    name: str
    visible: bool = True
    # (x, y, z) -> color index key or RGB tuple stored as "#RRGGBB"
    blocks: dict[tuple[int, int, int], str] = dataclasses.field(default_factory=dict)

    def block_count(self) -> int:
        """Return the number of voxels held by this layer."""
        return len(self.blocks)


@dataclasses.dataclass
class VoxelScene:
    """A named voxel grid with a colour palette and one or more layers."""

    name: str
    palette: dict[str, tuple[int, int, int]] = dataclasses.field(
        default_factory=lambda: dict(DEFAULT_PALETTE)
    )
    layers: list[VoxelLayer] = dataclasses.field(default_factory=list)
    active_layer: int = 0
    voxel_size: float = 1.0  # world units per grid step (0.25 = 4x finer detail)

    def __post_init__(self) -> None:
        """Guarantee that the scene always owns at least one layer."""
        if not self.layers:
            self.layers.append(VoxelLayer(name="Layer 1"))

    @property
    def layer(self) -> VoxelLayer:
        """The currently active layer."""
        return self.layers[self.active_layer]

    def add_layer(self, name: str) -> VoxelLayer:
        """Append a new empty layer and return it."""
        layer = VoxelLayer(name=name)
        self.layers.append(layer)
        return layer

    def set_palette_color(self, key: str, r: int, g: int, b: int) -> None:
        """Bind a palette key to a validated 24-bit RGB colour."""
        self.palette[str(key)] = validate_rgb((r, g, b))

    def resolve_color(self, color: str) -> tuple[int, int, int]:
        """Return the RGB triple for a palette key or ``#RRGGBB`` literal.

        Parameters
        ----------
        color
            A palette key such as ``"2"``, or a hex literal such as
            ``"#123456"``.

        Returns
        -------
        tuple of int
            The red, green, and blue channel values.

        Raises
        ------
        ValueError
            If the colour is neither a known palette key nor a hex literal.
        """
        if color in self.palette:
            return self.palette[color]
        msg = f"unknown colour '{color}'; use a palette key or #RRGGBB"
        if color.startswith("#") and len(color) == HEX_COLOUR_LENGTH:
            try:
                return (
                    int(color[1:3], 16),
                    int(color[3:5], 16),
                    int(color[5:7], 16),
                )
            except ValueError as exc:
                raise ValueError(msg) from exc
        raise ValueError(msg)

    def _resolve_layer_index(self, layer_index: int | None) -> int:
        """Return a validated layer index, defaulting to the active layer."""
        index = layer_index if layer_index is not None else self.active_layer
        if not 0 <= index < len(self.layers):
            msg = f"layer_index must be between 0 and {len(self.layers) - 1}"
            raise ValueError(msg)
        return index

    # The flat coordinate signatures below are the published contract; the MCP
    # server, the editor bridge, and the procedural builders all pass the
    # coordinates positionally.
    # pylint: disable=R0913,R0917  # flat coordinate signatures are the contract
    def place(  # ruff: ignore[too-many-arguments, too-many-positional-arguments]  # flat signature is the public contract
        self,
        x: int,
        y: int,
        z: int,
        color: str = "1",
        layer_index: int | None = None,
    ) -> None:
        """Set the voxel at ``(x, y, z)`` to the given colour.

        The colour is resolved before the layer index, so an unknown colour
        leaves the scene untouched.
        """
        self.resolve_color(color)
        index = self._resolve_layer_index(layer_index)
        self.layers[index].blocks[int(x), int(y), int(z)] = color

    def remove(self, x: int, y: int, z: int, layer_index: int | None = None) -> bool:
        """Delete the voxel at ``(x, y, z)`` and report whether one was there."""
        index = self._resolve_layer_index(layer_index)
        return self.layers[index].blocks.pop((int(x), int(y), int(z)), None) is not None

    def fill_box(  # ruff: ignore[too-many-arguments, too-many-positional-arguments]  # flat signature is the public contract
        self,
        x1: int,
        x2: int,
        y1: int,
        y2: int,
        z1: int,
        z2: int,
        color: str = "1",
        layer_index: int | None = None,
    ) -> int:
        """Fill an inclusive axis-aligned box and return the voxel count."""
        count = 0
        for x in range(min(x1, x2), max(x1, x2) + 1):
            for y in range(min(y1, y2), max(y1, y2) + 1):
                for z in range(min(z1, z2), max(z1, z2) + 1):
                    self.place(x, y, z, color, layer_index)
                    count += 1
        return count

    # pylint: enable=R0913,R0917  # restore the argument-count gate

    def clear(self, layer_index: int | None = None) -> None:
        """Empty one layer, or every layer when no index is given."""
        if layer_index is None:
            for layer in self.layers:
                layer.blocks.clear()
        else:
            self.layers[layer_index].blocks.clear()

    def all_blocks(self) -> list[tuple[int, int, int, str, str]]:
        """Return (x,y,z,color,layer_name) for all visible layers."""
        out: list[tuple[int, int, int, str, str]] = []
        for layer in self.layers:
            if not layer.visible:
                continue
            for (x, y, z), color in layer.blocks.items():
                out.append((x, y, z, color, layer.name))
        return out

    def block_count(self) -> int:
        """Return the number of voxels across every layer, hidden included."""
        return sum(layer.block_count() for layer in self.layers)

    def bounds(self) -> dict[str, int] | None:
        """Return the inclusive extent of the visible voxels, or ``None``.

        ``None`` means no visible layer holds any voxel.
        """
        blocks = self.all_blocks()
        if not blocks:
            return None
        xs = [b[0] for b in blocks]
        ys = [b[1] for b in blocks]
        zs = [b[2] for b in blocks]
        return {
            "minX": min(xs),
            "maxX": max(xs),
            "minY": min(ys),
            "maxY": max(ys),
            "minZ": min(zs),
            "maxZ": max(zs),
        }

    def to_dict(self) -> dict[str, typ.Any]:
        """Return the JSON-serializable form of the scene."""
        return {
            "name": self.name,
            "voxel_size": self.voxel_size,
            "palette": {k: list(v) for k, v in self.palette.items()},
            "active_layer": self.active_layer,
            "layers": [
                {
                    "name": layer.name,
                    "visible": layer.visible,
                    "blocks": [
                        [x, y, z, c] for (x, y, z), c in sorted(layer.blocks.items())
                    ],
                }
                for layer in self.layers
            ],
        }

    @classmethod
    def from_dict(cls, data: dict[str, typ.Any]) -> VoxelScene:
        """Rebuild a scene from the dictionary produced by :meth:`to_dict`.

        Every field is validated, so a malformed document raises rather than
        producing a partially populated scene: ``TypeError`` when a field has
        the wrong JSON type, ``ValueError`` when its content is unusable.
        """
        if not isinstance(data, dict):
            msg = "scene must be a JSON object"
            raise TypeError(msg)
        name = validate_scene_name(str(data.get("name", "Unnamed")))
        active_layer = int(data.get("active_layer", 0))
        voxel_size = validate_voxel_size(float(data.get("voxel_size", 1.0)))
        scene = cls(name=name, active_layer=active_layer, voxel_size=voxel_size)
        scene.layers.clear()
        _load_palette(scene, data.get("palette") or {})
        _load_layers(scene, data.get("layers", []))
        if not scene.layers:
            scene.layers.append(VoxelLayer(name="Layer 1"))
        if not 0 <= active_layer < len(scene.layers):
            msg = f"active_layer must be between 0 and {len(scene.layers) - 1}"
            raise ValueError(msg)
        return scene

    def save(self) -> Path:
        """Write the scene to the user scene directory and return its path."""
        path = _data_dir() / f"{validate_scene_name(self.name)}.json"
        path.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return path

    @classmethod
    def load(cls, name: str) -> VoxelScene:
        """Read a previously saved scene by name.

        Raises
        ------
        FileNotFoundError
            If no scene of that name has been saved.
        """
        path = _data_dir() / f"{validate_scene_name(name)}.json"
        if not path.exists():
            msg = f"ไม่พบ scene '{name}' ที่ {path}"
            raise FileNotFoundError(msg)
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))

    @staticmethod
    def list_saved() -> list[str]:
        """Return the sorted names of every saved scene."""
        return sorted(p.stem for p in _data_dir().glob("*.json"))


def _load_palette(scene: VoxelScene, palette: object) -> None:
    """Merge validated palette entries from serialized data into the scene."""
    if not isinstance(palette, dict):
        msg = "palette must be a JSON object"
        raise TypeError(msg)
    for key, value in palette.items():
        if not isinstance(value, (list, tuple)) or len(value) != RGB_CHANNEL_COUNT:
            msg = f"palette colour {key!r} must contain three channels"
            raise ValueError(msg)
        scene.palette[str(key)] = validate_rgb(value)


def _load_layers(scene: VoxelScene, layers_data: object) -> None:
    """Append every serialized layer, in order, to the scene."""
    if not isinstance(layers_data, list):
        msg = "layers must be a JSON array"
        raise TypeError(msg)
    for layer_data in layers_data:
        if not isinstance(layer_data, dict):
            msg = "each layer must be a JSON object"
            raise TypeError(msg)
        layer = VoxelLayer(
            name=str(layer_data.get("name", "Layer")),
            visible=bool(layer_data.get("visible", True)),
        )
        _load_blocks(scene, layer, layer_data.get("blocks", []))
        scene.layers.append(layer)


def _load_blocks(scene: VoxelScene, layer: VoxelLayer, blocks: object) -> None:
    """Populate a layer from serialized ``[x, y, z, colour]`` rows."""
    if not isinstance(blocks, list):
        msg = "layer blocks must be a JSON array"
        raise TypeError(msg)
    for row in blocks:
        if not isinstance(row, (list, tuple)) or len(row) != BLOCK_ROW_LENGTH:
            msg = "each block must be [x, y, z, colour]"
            raise ValueError(msg)
        colour = str(row[3])
        scene.resolve_color(colour)
        layer.blocks[int(row[0]), int(row[1]), int(row[2])] = colour


class SceneStore:
    """In-memory scene registry for MCP session."""

    def __init__(self) -> None:
        """Create an empty registry with no current scene."""
        self._scenes: dict[str, VoxelScene] = {}
        self._current: str | None = None

    def create(self, name: str) -> VoxelScene:
        """Register a new empty scene and make it current."""
        scene = VoxelScene(name=validate_scene_name(name))
        self._scenes[scene.name] = scene
        self._current = scene.name
        return scene

    def get(self, name: str | None = None) -> VoxelScene:
        """Return a registered scene by name, or the current one.

        Raises
        ------
        KeyError
            If the name is unknown, or no scene is current.
        """
        key = name or self._current
        if not key or key not in self._scenes:
            msg = "ยังไม่มี scene — เรียก voxelforge_create_scene ก่อน"
            raise KeyError(msg)
        return self._scenes[key]

    def set_current(self, name: str) -> VoxelScene:
        """Make the named scene current, loading it from disk if needed."""
        if name not in self._scenes:
            self._scenes[name] = VoxelScene.load(name)
        self._current = name
        return self._scenes[name]

    def list_active(self) -> list[str]:
        """Return the sorted names of every scene held in memory."""
        return sorted(self._scenes.keys())
