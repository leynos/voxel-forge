"""Qt3D viewport rendering voxels as merged boxes (fast, and true to export)."""

from __future__ import annotations

import typing as typ

from PySide6.Qt3DCore import Qt3DCore
from PySide6.Qt3DExtras import Qt3DExtras
from PySide6.Qt3DRender import Qt3DRender
from PySide6.QtCore import QSize
from PySide6.QtGui import QColor, QVector3D, QWindow
from PySide6.QtWidgets import QWidget

from voxel_forge.mesh_merge import merge_scene

if typ.TYPE_CHECKING:
    from voxel_forge.mesh_merge import MergedBox
    from voxel_forge.model import VoxelScene

# Qt3D rejects a zero extent, so degenerate boxes keep a sliver of size.
MIN_EXTENT = 0.01


def _box_mesh(
    entity: Qt3DCore.QEntity, box: MergedBox, vs: float
) -> Qt3DExtras.QCuboidMesh:
    mesh = Qt3DExtras.QCuboidMesh(entity)
    mesh.setXExtent(max((box.x2 - box.x1 + 1) * vs, MIN_EXTENT))
    mesh.setYExtent(max((box.y2 - box.y1 + 1) * vs, MIN_EXTENT))
    mesh.setZExtent(max((box.z2 - box.z1 + 1) * vs, MIN_EXTENT))
    return mesh


def _box_transform(
    entity: Qt3DCore.QEntity, box: MergedBox, vs: float
) -> Qt3DCore.QTransform:
    transform = Qt3DCore.QTransform(entity)
    cx = (box.x1 + box.x2 + 1) * 0.5 * vs
    cy = (box.y1 + box.y2 + 1) * 0.5 * vs
    cz = (box.z1 + box.z2 + 1) * 0.5 * vs
    transform.setTranslation(QVector3D(cx, cy, cz))
    return transform


def _box_material(
    entity: Qt3DCore.QEntity, rgb: tuple[int, int, int]
) -> Qt3DExtras.QPhongMaterial:
    r, g, b = rgb
    material = Qt3DExtras.QPhongMaterial(entity)
    material.setDiffuse(QColor(r, g, b))
    material.setAmbient(QColor(int(r * 0.35), int(g * 0.35), int(b * 0.35)))
    material.setSpecular(QColor(40, 40, 40))
    material.setShininess(20.0)
    return material


class VoxelViewport(QWindow):
    """Qt3D window that renders a scene as merged, coloured cuboids."""

    def __init__(self) -> None:
        super().__init__()
        self.resize(QSize(1280, 720))

        self._view = Qt3DExtras.Qt3DWindow()
        self._view.defaultFrameGraph().setClearColor(QColor(26, 26, 46))

        self._root = Qt3DCore.QEntity()
        self._boxes_root = Qt3DCore.QEntity(self._root)

        camera = self._view.camera()
        camera.lens().setPerspectiveProjection(45.0, 16.0 / 9.0, 0.1, 1000.0)
        camera.setPosition(QVector3D(14, 12, 14))
        camera.setViewCenter(QVector3D(2, 4, 2))

        self._controller = Qt3DExtras.QOrbitCameraController(self._root)
        self._controller.setCamera(camera)
        self._controller.setLinearSpeed(50.0)
        self._controller.setLookSpeed(180.0)

        light = Qt3DCore.QEntity(self._root)
        light_comp = Qt3DRender.QDirectionalLight(light)
        light_comp.setColor(QColor(255, 255, 255))
        light_comp.setIntensity(0.9)
        light_comp.setWorldDirection(QVector3D(-0.5, -1.0, -0.3))
        light_transform = Qt3DCore.QTransform(light)
        light.addComponent(light_comp)
        light.addComponent(light_transform)

        ambient = Qt3DCore.QEntity(self._root)
        amb = Qt3DRender.QDirectionalLight(ambient)
        amb.setColor(QColor(120, 140, 200))
        amb.setIntensity(0.25)
        amb.setWorldDirection(QVector3D(0.3, -0.5, 0.8))
        ambient.addComponent(amb)

        self._view.setRootEntity(self._root)
        self._scene: VoxelScene | None = None

    def embed_widget(self) -> QWidget:
        """Return a widget container that hosts the Qt3D window."""
        return QWidget.createWindowContainer(self._view)

    def load_scene(self, scene: VoxelScene) -> None:
        """Render a scene as merged boxes and frame the camera on it.

        Parameters
        ----------
        scene
            Scene to render; its visible layers are merged into cuboids.
        """
        self._scene = scene
        self._clear_boxes()

        vs = scene.voxel_size
        boxes = merge_scene(scene)

        for box in boxes:
            self._add_box(box, scene, vs)

        self._frame_camera(scene)

    def reset_camera(self) -> None:
        """Frame the camera on the loaded scene, if there is one."""
        if self._scene:
            self._frame_camera(self._scene)

    def _clear_boxes(self) -> None:
        # Detaching the box root discards every entity parented to it.
        self._boxes_root.setParent(None)  # type: ignore[union-attr]  # Qt allows None.
        self._boxes_root = Qt3DCore.QEntity(self._root)

    def _add_box(self, box: MergedBox, scene: VoxelScene, vs: float) -> None:
        entity = Qt3DCore.QEntity(self._boxes_root)
        entity.addComponent(_box_mesh(entity, box, vs))
        entity.addComponent(_box_transform(entity, box, vs))
        entity.addComponent(_box_material(entity, scene.resolve_color(box.color)))

    def _frame_camera(self, scene: VoxelScene) -> None:
        b = scene.bounds()
        if not b:
            return
        vs = scene.voxel_size
        cx = (b["minX"] + b["maxX"] + 1) * 0.5 * vs
        cy = (b["minY"] + b["maxY"] + 1) * 0.5 * vs
        cz = (b["minZ"] + b["maxZ"] + 1) * 0.5 * vs
        span = (
            max(b["maxX"] - b["minX"], b["maxY"] - b["minY"], b["maxZ"] - b["minZ"], 4)
            * vs
        )

        cam = self._view.camera()
        cam.setViewCenter(QVector3D(cx, cy, cz))
        cam.setPosition(QVector3D(cx + span * 1.6, cy + span * 1.2, cz + span * 1.6))
