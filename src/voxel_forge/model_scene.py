"""Voxel scene state and mutations; persistence belongs to scene_store."""

from __future__ import annotations

import dataclasses
import typing as typ

from .model_decode import _parse_layers, _parse_palette
from .model_layer import VoxelLayer
from .model_validation import (
    DEFAULT_PALETTE,
    InvalidSceneDataError,
    _require_text,
    _validate_rgb,
    _validate_voxel_size,
    resolve_palette_colour,
    validate_layer_index,
    validate_scene_name,
)


@dataclasses.dataclass(slots=True)
class VoxelScene:
    """A layered voxel scene with a 24-bit RGB palette."""

    name: str
    palette: dict[str, tuple[int, int, int]] = dataclasses.field(
        default_factory=lambda: dict(DEFAULT_PALETTE)
    )
    layers: list[VoxelLayer] = dataclasses.field(default_factory=list)
    active_layer: int = 0
    voxel_size: float = 1.0  # world units per grid step (0.25 = 4x finer detail)

    def __post_init__(self) -> None:
        """Ensure an empty scene always has its initial layer."""
        if not self.layers:
            self.layers.append(VoxelLayer(name="Layer 1"))

    @property
    def layer(self) -> VoxelLayer:
        """Currently active layer."""
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

    # The flat coordinate signatures below are the published contract; the MCP
    # server, the editor bridge, and the procedural builders all pass the
    # coordinates positionally.
    # pylint: disable=R0913,R0917  # flat coordinate signatures are the contract
    def place(  # ruff: ignore[too-many-arguments, too-many-positional-arguments]  # flat signature is the public contract
        self, x: int, y: int, z: int, color: str = "1", layer_index: int | None = None
    ) -> None:
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
        validate_layer_index(index, len(self.layers))
        self.layers[index].blocks[int(x), int(y), int(z)] = color

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
        validate_layer_index(index, len(self.layers))
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

    def to_dict(self) -> dict[str, typ.Any]:
        """
        Return a JSON-serialisable representation of the whole scene.

        Returns
        -------
        dict[str, typ.Any]
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
                    "blocks": [
                        [x, y, z, c] for (x, y, z), c in sorted(layer.blocks.items())
                    ],
                }
                for layer in self.layers
            ],
        }

    @classmethod
    def from_dict(cls, data: dict[str, typ.Any]) -> VoxelScene:
        """
        Build a scene from untrusted JSON-derived data.

        Each schema boundary — scene fields, palette, layers, and block rows —
        is validated by its own helper so failures name the offending field.

        Parameters
        ----------
        data : dict[str, typ.Any]
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
            msg = "scene must be a JSON object"
            raise InvalidSceneDataError(msg)
        name = validate_scene_name(
            _require_text(data.get("name", "Unnamed"), "scene name")
        )
        active_layer = int(data.get("active_layer", 0))
        voxel_size = _validate_voxel_size(data.get("voxel_size", 1.0))
        palette = _parse_palette(data.get("palette"))
        layers = _parse_layers(data.get("layers", []), palette)
        if not layers:
            layers.append(VoxelLayer(name="Layer 1"))
        validate_layer_index(active_layer, len(layers), field_name="active_layer")
        return cls(
            name=name,
            palette=palette,
            layers=layers,
            active_layer=active_layer,
            voxel_size=voxel_size,
        )
