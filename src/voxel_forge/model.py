"""Core voxel scene model — layers, 24-bit RGB, Goxel/MagicaVoxel compatible grid.

This module is pure domain: it describes scenes, layers, palettes, and the
validation rules for untrusted data, and it performs no file I/O. Persistence
lives in :mod:`voxel_forge.scene_store`.
"""

from __future__ import annotations

import math
import threading
from collections.abc import Mapping
from dataclasses import dataclass, field
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

MIN_SCENE_NAME_LENGTH = 1
MAX_SCENE_NAME_LENGTH = 80
MIN_VOXEL_SIZE = 0.05
MAX_VOXEL_SIZE = 2.0

_INVALID_SCENE_NAME_CHARS = frozenset('<>:"/\\|?*')
_WINDOWS_RESERVED_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"} | {f"COM{index}" for index in range(1, 10)} | {f"LPT{index}" for index in range(1, 10)}
)


def validate_scene_name(name: str) -> str:
    """
    Validate a scene name for use as a cross-platform filename component.

    Parameters
    ----------
    name : str
        Candidate scene name. The name is stored verbatim and must be a safe
        filename component on Windows, macOS, and Linux.

    Returns
    -------
    str
        The validated name, unchanged.

    Raises
    ------
    ValueError
        If ``name`` is not text, is empty, is longer than
        ``MAX_SCENE_NAME_LENGTH``, has leading or trailing whitespace, contains
        path separators, control characters, or other characters Windows
        forbids, or is a reserved Windows device name.
    """
    if not isinstance(name, str):
        raise ValueError("scene name must be text")
    _reject_unsafe_scene_name(name)
    _reject_reserved_scene_name(name)
    return name


def _reject_unsafe_scene_name(name: str) -> None:
    """Reject scene names that are empty, over-long, or contain forbidden characters."""
    if not name or name != name.strip() or len(name) > MAX_SCENE_NAME_LENGTH:
        raise ValueError(
            f"scene name must contain {MIN_SCENE_NAME_LENGTH} to {MAX_SCENE_NAME_LENGTH} non-edge-whitespace characters"
        )
    if name in {".", ".."} or any(character in _INVALID_SCENE_NAME_CHARS for character in name):
        raise ValueError("scene name cannot contain path or filename separators")
    if any(ord(character) < 32 for character in name):
        raise ValueError("scene name cannot contain control characters")


def _reject_reserved_scene_name(name: str) -> None:
    """Reject scene names Windows reserves, including device names with extensions."""
    stem = name.split(".", 1)[0].upper()
    if stem in _WINDOWS_RESERVED_NAMES or name.endswith((".", " ")):
        raise ValueError("scene name is reserved by Windows")


def _validate_rgb(rgb: tuple[int, int, int] | list[int], *, field_name: str = "palette") -> tuple[int, int, int]:
    """Return three integer RGB channels in 0..255, rejecting booleans and other non-integers."""
    if not isinstance(rgb, (list, tuple)) or len(rgb) != 3:
        raise ValueError(f"{field_name} colours require three channels in the range 0..255")
    if any(type(channel) is not int or channel < 0 or channel > 255 for channel in rgb):
        raise ValueError(f"{field_name} colours require three integer channels in the range 0..255")
    return rgb[0], rgb[1], rgb[2]


def resolve_palette_colour(palette: Mapping[str, tuple[int, int, int]], color: str) -> tuple[int, int, int]:
    """
    Resolve a palette key or ``#RRGGBB`` literal into 24-bit RGB.

    Parameters
    ----------
    palette : Mapping[str, tuple[int, int, int]]
        Palette mapping colour keys to RGB triples.
    color : str
        A palette key, or a ``#RRGGBB`` hexadecimal literal.

    Returns
    -------
    tuple[int, int, int]
        The resolved ``(r, g, b)`` triple.

    Raises
    ------
    ValueError
        If ``color`` is neither a palette key nor a well-formed ``#RRGGBB``
        literal.
    """
    if color in palette:
        return palette[color]
    if color.startswith("#") and len(color) == 7:
        try:
            return (
                int(color[1:3], 16),
                int(color[3:5], 16),
                int(color[5:7], 16),
            )
        except ValueError as exc:
            raise ValueError(f"unknown colour '{color}'; use a palette key or #RRGGBB") from exc
    raise ValueError(f"unknown colour '{color}'; use a palette key or #RRGGBB")


def _validate_voxel_size(value: Any) -> float:
    """Return the voxel size as a finite float inside the supported range."""
    voxel_size = float(value)
    if not math.isfinite(voxel_size) or not MIN_VOXEL_SIZE <= voxel_size <= MAX_VOXEL_SIZE:
        raise ValueError(f"voxel_size must be a finite number between {MIN_VOXEL_SIZE} and {MAX_VOXEL_SIZE}")
    return voxel_size


def _parse_palette(raw: Any) -> dict[str, tuple[int, int, int]]:
    """Return the default palette with any scene-supplied overrides applied."""
    palette = dict(DEFAULT_PALETTE)
    if raw is None:
        return palette
    if not isinstance(raw, dict):
        raise ValueError("palette must be a JSON object")
    for key, value in raw.items():
        if not isinstance(value, (list, tuple)) or len(value) != 3:
            raise ValueError(f"palette colour {key!r} must contain three channels")
        palette[str(key)] = _validate_rgb(value)
    return palette


def _parse_block(row: Any, palette: Mapping[str, tuple[int, int, int]]) -> tuple[tuple[int, int, int], str]:
    """Return the coordinate and validated colour of one serialised block row."""
    if not isinstance(row, (list, tuple)) or len(row) != 4:
        raise ValueError("each block must be [x, y, z, colour]")
    colour = str(row[3])
    resolve_palette_colour(palette, colour)
    return (int(row[0]), int(row[1]), int(row[2])), colour


def _parse_layer(raw: Any, palette: Mapping[str, tuple[int, int, int]]) -> VoxelLayer:
    """Build one layer, validating its schema boundary and every block row."""
    if not isinstance(raw, dict):
        raise ValueError("each layer must be a JSON object")
    layer = VoxelLayer(
        name=str(raw.get("name", "Layer")),
        visible=bool(raw.get("visible", True)),
    )
    blocks = raw.get("blocks", [])
    if not isinstance(blocks, list):
        raise ValueError("layer blocks must be a JSON array")
    for row in blocks:
        coordinate, colour = _parse_block(row, palette)
        layer.blocks[coordinate] = colour
    return layer


def _parse_layers(raw: Any, palette: Mapping[str, tuple[int, int, int]]) -> list[VoxelLayer]:
    """Build every layer described by a serialised scene."""
    if not isinstance(raw, list):
        raise ValueError("layers must be a JSON array")
    return [_parse_layer(entry, palette) for entry in raw]


@dataclass(slots=True)
class VoxelLayer:
    """One named, optionally hidden layer of voxels."""

    name: str
    visible: bool = True
    # (x, y, z) -> color index key or RGB tuple stored as "#RRGGBB"
    blocks: dict[tuple[int, int, int], str] = field(default_factory=dict)

    def block_count(self) -> int:
        """
        Return the number of voxels held by this layer.

        Returns
        -------
        int
            Count of coordinates currently occupied in this layer.
        """
        return len(self.blocks)


@dataclass(slots=True)
class VoxelScene:
    """A layered voxel scene with a 24-bit RGB palette."""

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
        """Return the currently active layer."""
        return self.layers[self.active_layer]

    def add_layer(self, name: str) -> VoxelLayer:
        """
        Append a new, empty layer and return it.

        Parameters
        ----------
        name : str
            Display name for the new layer.

        Returns
        -------
        VoxelLayer
            The newly created layer.
        """
        layer = VoxelLayer(name=name)
        self.layers.append(layer)
        return layer

    def set_palette_color(self, key: str, r: int, g: int, b: int) -> None:
        """
        Assign an RGB triple to a palette key.

        Parameters
        ----------
        key : str
            Palette key to create or overwrite.
        r, g, b : int
            Integer channels in the inclusive range 0..255.

        Raises
        ------
        ValueError
            If any channel is not an integer in the range 0..255.
        """
        self.palette[str(key)] = _validate_rgb((r, g, b))

    def resolve_color(self, color: str) -> tuple[int, int, int]:
        """
        Resolve a palette key or ``#RRGGBB`` literal into 24-bit RGB.

        Parameters
        ----------
        color : str
            A palette key, or a ``#RRGGBB`` hexadecimal literal.

        Returns
        -------
        tuple[int, int, int]
            The resolved ``(r, g, b)`` triple.

        Raises
        ------
        ValueError
            If ``color`` cannot be resolved.
        """
        return resolve_palette_colour(self.palette, color)

    def place(self, x: int, y: int, z: int, color: str = "1", layer_index: int | None = None) -> None:
        """
        Set one voxel, replacing any voxel already at that coordinate.

        Parameters
        ----------
        x, y, z : int
            Grid coordinate of the voxel.
        color : str, optional
            Palette key or ``#RRGGBB`` literal. Defaults to ``"1"``.
        layer_index : int | None, optional
            Target layer. Defaults to the active layer.

        Raises
        ------
        ValueError
            If ``color`` cannot be resolved or ``layer_index`` is out of range.
            The scene is left unmodified when either check fails.
        """
        self.resolve_color(color)
        index = layer_index if layer_index is not None else self.active_layer
        if index < 0 or index >= len(self.layers):
            raise ValueError(f"layer_index must be between 0 and {len(self.layers) - 1}")
        self.layers[index].blocks[(int(x), int(y), int(z))] = color

    def remove(self, x: int, y: int, z: int, layer_index: int | None = None) -> bool:
        """
        Delete one voxel.

        Parameters
        ----------
        x, y, z : int
            Grid coordinate of the voxel.
        layer_index : int | None, optional
            Source layer. Defaults to the active layer.

        Returns
        -------
        bool
            ``True`` when a voxel was removed, ``False`` when the coordinate
            held no voxel.

        Raises
        ------
        ValueError
            If ``layer_index`` is out of range.
        """
        index = layer_index if layer_index is not None else self.active_layer
        if index < 0 or index >= len(self.layers):
            raise ValueError(f"layer_index must be between 0 and {len(self.layers) - 1}")
        return self.layers[index].blocks.pop((int(x), int(y), int(z)), None) is not None

    def remove_from_any_layer(self, x: int, y: int, z: int) -> bool:
        """
        Delete the topmost voxel at a coordinate, whichever layer holds it.

        Parameters
        ----------
        x, y, z : int
            Grid coordinate of the voxel.

        Returns
        -------
        bool
            ``True`` when a voxel was removed, ``False`` when no layer held the
            coordinate.

        Notes
        -----
        The web editor merges visible layers for rendering, so a picked voxel's
        own layer is not always the active one. Removing from visible layers
        last-to-first mirrors the render order, which makes the voxel the user
        actually sees disappear first.
        """
        coordinate = (int(x), int(y), int(z))
        for layer in reversed(self.layers):
            if not layer.visible:
                continue
            if layer.blocks.pop(coordinate, None) is not None:
                return True
        return False

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
        """
        Fill an axis-aligned box with voxels.

        Parameters
        ----------
        x1, x2, y1, y2, z1, z2 : int
            Inclusive bounds on each axis; the order of each pair is irrelevant.
        color : str, optional
            Palette key or ``#RRGGBB`` literal. Defaults to ``"1"``.
        layer_index : int | None, optional
            Target layer. Defaults to the active layer.

        Returns
        -------
        int
            Number of voxels written.

        Raises
        ------
        ValueError
            If ``color`` is not a palette key or valid ``#RRGGBB`` literal, or
            ``layer_index`` names no layer. Raised by :meth:`place` on the
            first voxel, before any later voxel is written.
        """
        count = 0
        for x in range(min(x1, x2), max(x1, x2) + 1):
            for y in range(min(y1, y2), max(y1, y2) + 1):
                for z in range(min(z1, z2), max(z1, z2) + 1):
                    self.place(x, y, z, color, layer_index)
                    count += 1
        return count

    def clear(self, layer_index: int | None = None) -> None:
        """
        Delete every voxel in one layer, or in every layer.

        Parameters
        ----------
        layer_index : int | None, optional
            Layer to clear. ``None`` clears all layers.
        """
        if layer_index is None:
            for layer in self.layers:
                layer.blocks.clear()
        else:
            self.layers[layer_index].blocks.clear()

    def all_blocks(self) -> list[tuple[int, int, int, str, str]]:
        """
        Return (x,y,z,color,layer_name) for all visible layers.

        Returns
        -------
        list[tuple[int, int, int, str, str]]
            One tuple per voxel: its coordinates, the palette key or
            ``#RRGGBB`` colour it carries, and the name of the layer holding
            it. Voxels in hidden layers are excluded.
        """
        out: list[tuple[int, int, int, str, str]] = []
        for layer in self.layers:
            if not layer.visible:
                continue
            for (x, y, z), color in layer.blocks.items():
                out.append((x, y, z, color, layer.name))
        return out

    def block_count(self) -> int:
        """
        Return the total number of voxels across all layers, visible or not.

        Returns
        -------
        int
            Sum of every layer's voxel count, including hidden layers.
        """
        return sum(map(VoxelLayer.block_count, self.layers))

    def bounds(self) -> dict[str, int] | None:
        """
        Return the inclusive bounding box of all visible voxels.

        Returns
        -------
        dict[str, int] | None
            ``minX``/``maxX``/``minY``/``maxY``/``minZ``/``maxZ`` keys, or
            ``None`` when no visible voxel exists.
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

    def to_dict(self) -> dict[str, Any]:
        """
        Return a JSON-serialisable representation of the whole scene.

        Returns
        -------
        dict[str, Any]
            A mapping with ``name``, ``voxel_size``, ``palette`` (colour keys
            mapped to ``[r, g, b]`` lists), ``active_layer``, and ``layers``.
            Each layer holds its ``name``, ``visible`` flag, and ``blocks`` as
            ``[x, y, z, color]`` rows sorted by coordinate.
        """
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
        """
        Build a scene from untrusted JSON-derived data.

        Each schema boundary — scene fields, palette, layers, and block rows —
        is validated by its own helper so failures name the offending field.

        Parameters
        ----------
        data : dict[str, Any]
            Mapping produced by ``json.loads``, typically from a scene file or
            an editor ``POST /scene`` request.

        Returns
        -------
        VoxelScene
            The validated scene.

        Raises
        ------
        ValueError
            If the payload is not a JSON object, or the scene name, voxel size,
            palette, layers, block rows, or active layer index are invalid.
        """
        if not isinstance(data, dict):
            raise ValueError("scene must be a JSON object")
        name = validate_scene_name(_require_text(data.get("name", "Unnamed"), "scene name"))
        active_layer = int(data.get("active_layer", 0))
        voxel_size = _validate_voxel_size(data.get("voxel_size", 1.0))
        palette = _parse_palette(data.get("palette"))
        layers = _parse_layers(data.get("layers", []), palette)
        if not layers:
            layers.append(VoxelLayer(name="Layer 1"))
        if active_layer < 0 or active_layer >= len(layers):
            raise ValueError(f"active_layer must be between 0 and {len(layers) - 1}")
        return cls(
            name=name,
            palette=palette,
            layers=layers,
            active_layer=active_layer,
            voxel_size=voxel_size,
        )


def _require_text(value: Any, field_name: str) -> str:
    """Return ``value`` when it is text, otherwise raise ``ValueError``."""
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be text")
    return value


class SceneStore:
    """
    In-memory scene registry for the MCP session, and the owner of scene state.

    One store instance is the single owner of the registry. The MCP tool
    surface and the editor bridge hold a reference to that same instance
    (``bridge.store`` is set to the server's store, not copied) and mutate
    scenes only while holding :attr:`lock`. The store's own methods take the
    lock for the registry operation itself; a caller that needs the mutation
    and its snapshot to be one atomic step holds the lock across both, which is
    what keeps a reader on another thread from seeing a half-written scene.
    """

    def __init__(self) -> None:
        self._scenes: dict[str, VoxelScene] = {}
        self._current: str | None = None
        self._lock = threading.RLock()

    @property
    def lock(self) -> threading.RLock:
        """
        Return the re-entrant lock guarding scene reads and mutations.

        Returns
        -------
        threading.RLock
            The single lock shared by the MCP tool surface and the editor
            bridge. Hold it across a read-modify-snapshot sequence so that the
            mutation and the snapshot it feeds are one atomic step; the
            store's methods re-acquire it internally, which the re-entrant
            lock permits.
        """
        return self._lock

    def create(self, name: str) -> VoxelScene:
        """
        Register a new empty scene and make it current.

        Parameters
        ----------
        name : str
            Scene name, validated by ``validate_scene_name``.

        Returns
        -------
        VoxelScene
            The newly created scene.

        Raises
        ------
        ValueError
            If ``name`` is not a safe filename component on this platform:
            empty, over-long, edge-whitespaced, containing path separators or
            control characters, or a Windows-reserved device name. Raised by
            :func:`validate_scene_name` before any scene is registered.
        """
        scene = VoxelScene(name=validate_scene_name(name))
        self.register(scene)
        return scene

    def register(self, scene: VoxelScene) -> VoxelScene:
        """
        Adopt an existing scene and make it current.

        Parameters
        ----------
        scene : VoxelScene
            Scene to store, typically produced by loading or importing.

        Returns
        -------
        VoxelScene
            The same scene, now registered.
        """
        with self._lock:
            self._scenes[scene.name] = scene
            self._current = scene.name
        return scene

    def get(self, name: str | None = None) -> VoxelScene:
        """
        Return a registered scene.

        Parameters
        ----------
        name : str | None, optional
            Scene to return. Defaults to the current scene.

        Returns
        -------
        VoxelScene
            The registered scene.

        Raises
        ------
        KeyError
            If no scene is current, or the requested name is not registered.
        """
        with self._lock:
            key = name or self._current
            if not key or key not in self._scenes:
                raise KeyError("ยังไม่มี scene — เรียก voxelforge_create_scene ก่อน")
            return self._scenes[key]

    def get_or_none(self, name: str | None = None) -> VoxelScene | None:
        """
        Return a registered scene, or ``None`` when it is not present.

        This is the non-raising counterpart of :meth:`get`, for callers such as
        the editor bridge that must tolerate an absent scene instead of failing
        the request that named it.

        Parameters
        ----------
        name : str | None, optional
            Scene to return. Defaults to the current scene.

        Returns
        -------
        VoxelScene | None
            The registered scene, or ``None`` when no scene is current or the
            requested name is not registered.
        """
        with self._lock:
            key = name or self._current
            if not key:
                return None
            return self._scenes.get(key)

    def select(self, name: str) -> VoxelScene:
        """
        Make a registered scene current.

        Parameters
        ----------
        name : str
            Name of a scene already held in this session.

        Returns
        -------
        VoxelScene
            The selected scene.

        Raises
        ------
        KeyError
            If the name is not registered. Loading from disk is the caller's
            responsibility, so this registry stays free of file I/O.
        """
        with self._lock:
            if name not in self._scenes:
                raise KeyError(f"scene '{name}' is not loaded in this session")
            self._current = name
            return self._scenes[name]

    def list_active(self) -> list[str]:
        """
        Return the sorted names of every scene held in this session.

        Returns
        -------
        list[str]
            Registered scene names in ascending sort order.
        """
        with self._lock:
            return sorted(self._scenes.keys())
