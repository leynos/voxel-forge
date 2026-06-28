"""Core voxel scene model — layers, 24-bit RGB, Goxel/MagicaVoxel compatible grid."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

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
    root = Path.home() / ".voxel-forge" / "scenes"
    root.mkdir(parents=True, exist_ok=True)
    return root


@dataclass
class VoxelLayer:
    name: str
    visible: bool = True
    # (x, y, z) -> color index key or RGB tuple stored as "#RRGGBB"
    blocks: dict[tuple[int, int, int], str] = field(default_factory=dict)

    def block_count(self) -> int:
        return len(self.blocks)


@dataclass
class VoxelScene:
    name: str
    palette: dict[str, tuple[int, int, int]] = field(default_factory=lambda: dict(DEFAULT_PALETTE))
    layers: list[VoxelLayer] = field(default_factory=list)
    active_layer: int = 0
    voxel_size: float = 1.0  # world units per grid step (0.25 = 4x finer detail)

    def __post_init__(self) -> None:
        if not self.layers:
            self.layers.append(VoxelLayer(name="Layer 1"))

    @property
    def layer(self) -> VoxelLayer:
        return self.layers[self.active_layer]

    def add_layer(self, name: str) -> VoxelLayer:
        layer = VoxelLayer(name=name)
        self.layers.append(layer)
        return layer

    def set_palette_color(self, key: str, r: int, g: int, b: int) -> None:
        self.palette[key] = (int(r) & 255, int(g) & 255, int(b) & 255)

    def resolve_color(self, color: str) -> tuple[int, int, int]:
        if color in self.palette:
            return self.palette[color]
        if color.startswith("#") and len(color) == 7:
            return (
                int(color[1:3], 16),
                int(color[3:5], 16),
                int(color[5:7], 16),
            )
        raise KeyError(f"ไม่รู้จักสี '{color}' — ใช้ key ในพาเลตหรือ #RRGGBB")

    def place(self, x: int, y: int, z: int, color: str = "1", layer_index: int | None = None) -> None:
        layer = self.layers[layer_index if layer_index is not None else self.active_layer]
        layer.blocks[(int(x), int(y), int(z))] = color

    def remove(self, x: int, y: int, z: int, layer_index: int | None = None) -> bool:
        layer = self.layers[layer_index if layer_index is not None else self.active_layer]
        return layer.blocks.pop((int(x), int(y), int(z)), None) is not None

    def fill_box(
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
        count = 0
        for x in range(min(x1, x2), max(x1, x2) + 1):
            for y in range(min(y1, y2), max(y1, y2) + 1):
                for z in range(min(z1, z2), max(z1, z2) + 1):
                    self.place(x, y, z, color, layer_index)
                    count += 1
        return count

    def clear(self, layer_index: int | None = None) -> None:
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
        return sum(layer.block_count() for layer in self.layers)

    def bounds(self) -> dict[str, int] | None:
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

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "voxel_size": self.voxel_size,
            "palette": {k: list(v) for k, v in self.palette.items()},
            "active_layer": self.active_layer,
            "layers": [
                {
                    "name": layer.name,
                    "visible": layer.visible,
                    "blocks": [[x, y, z, c] for (x, y, z), c in sorted(layer.blocks.items())],
                }
                for layer in self.layers
            ],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VoxelScene:
        scene = cls(
            name=str(data.get("name", "Unnamed")),
            active_layer=int(data.get("active_layer", 0)),
            voxel_size=float(data.get("voxel_size", 1.0)),
        )
        scene.layers.clear()
        pal = data.get("palette") or {}
        for k, v in pal.items():
            if isinstance(v, (list, tuple)) and len(v) == 3:
                scene.palette[str(k)] = (int(v[0]), int(v[1]), int(v[2]))
        for layer_data in data.get("layers", []):
            layer = VoxelLayer(
                name=str(layer_data.get("name", "Layer")),
                visible=bool(layer_data.get("visible", True)),
            )
            for row in layer_data.get("blocks", []):
                if len(row) >= 4:
                    layer.blocks[(int(row[0]), int(row[1]), int(row[2]))] = str(row[3])
            scene.layers.append(layer)
        if not scene.layers:
            scene.layers.append(VoxelLayer(name="Layer 1"))
        scene.active_layer = min(scene.active_layer, len(scene.layers) - 1)
        return scene

    def save(self) -> Path:
        path = _data_dir() / f"{self.name}.json"
        path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    @classmethod
    def load(cls, name: str) -> VoxelScene:
        path = _data_dir() / f"{name}.json"
        if not path.exists():
            raise FileNotFoundError(f"ไม่พบ scene '{name}' ที่ {path}")
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))

    @staticmethod
    def list_saved() -> list[str]:
        return sorted(p.stem for p in _data_dir().glob("*.json"))


class SceneStore:
    """In-memory scene registry for MCP session."""

    def __init__(self) -> None:
        self._scenes: dict[str, VoxelScene] = {}
        self._current: str | None = None

    def create(self, name: str) -> VoxelScene:
        scene = VoxelScene(name=name)
        self._scenes[name] = scene
        self._current = name
        return scene

    def get(self, name: str | None = None) -> VoxelScene:
        key = name or self._current
        if not key or key not in self._scenes:
            raise KeyError("ยังไม่มี scene — เรียก voxelforge_create_scene ก่อน")
        return self._scenes[key]

    def set_current(self, name: str) -> VoxelScene:
        if name not in self._scenes:
            self._scenes[name] = VoxelScene.load(name)
        self._current = name
        return self._scenes[name]

    def list_active(self) -> list[str]:
        return sorted(self._scenes.keys())
