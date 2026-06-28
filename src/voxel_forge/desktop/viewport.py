"""Qt3D viewport — แสดง voxel แบบ merged boxes (ลื่น + ตรงกับ export)."""

from __future__ import annotations

from PySide6.Qt3DCore import Qt3DCore
from PySide6.Qt3DExtras import Qt3DExtras
from PySide6.Qt3DRender import Qt3DRender
from PySide6.QtCore import QSize, QUrl
from PySide6.QtGui import QColor, QVector3D, QWindow
from PySide6.QtWidgets import QWidget

from ..mesh_merge import merge_scene
from ..model import VoxelScene


class VoxelViewport(QWindow):
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
        return QWidget.createWindowContainer(self._view)

    def load_scene(self, scene: VoxelScene) -> None:
        self._scene = scene
        self._clear_boxes()

        vs = scene.voxel_size
        boxes = merge_scene(scene)

        for box in boxes:
            self._add_box(box, scene, vs)

        self._frame_camera(scene)

    def _clear_boxes(self) -> None:
        self._boxes_root.setParent(None)  # type: ignore[union-attr]
        self._boxes_root = Qt3DCore.QEntity(self._root)

    def _add_box(self, box, scene: VoxelScene, vs: float) -> None:
        entity = Qt3DCore.QEntity(self._boxes_root)

        sx = (box.x2 - box.x1 + 1) * vs
        sy = (box.y2 - box.y1 + 1) * vs
        sz = (box.z2 - box.z1 + 1) * vs

        mesh = Qt3DExtras.QCuboidMesh(entity)
        mesh.setXExtent(max(sx, 0.01))
        mesh.setYExtent(max(sy, 0.01))
        mesh.setZExtent(max(sz, 0.01))

        transform = Qt3DCore.QTransform(entity)
        cx = (box.x1 + box.x2 + 1) * 0.5 * vs
        cy = (box.y1 + box.y2 + 1) * 0.5 * vs
        cz = (box.z1 + box.z2 + 1) * 0.5 * vs
        transform.setTranslation(QVector3D(cx, cy, cz))

        r, g, b = scene.resolve_color(box.color)
        material = Qt3DExtras.QPhongMaterial(entity)
        material.setDiffuse(QColor(r, g, b))
        material.setAmbient(QColor(int(r * 0.35), int(g * 0.35), int(b * 0.35)))
        material.setSpecular(QColor(40, 40, 40))
        material.setShininess(20.0)

        entity.addComponent(mesh)
        entity.addComponent(transform)
        entity.addComponent(material)

    def _frame_camera(self, scene: VoxelScene) -> None:
        b = scene.bounds()
        if not b:
            return
        vs = scene.voxel_size
        cx = (b["minX"] + b["maxX"] + 1) * 0.5 * vs
        cy = (b["minY"] + b["maxY"] + 1) * 0.5 * vs
        cz = (b["minZ"] + b["maxZ"] + 1) * 0.5 * vs
        span = max(b["maxX"] - b["minX"], b["maxY"] - b["minY"], b["maxZ"] - b["minZ"], 4) * vs

        cam = self._view.camera()
        cam.setViewCenter(QVector3D(cx, cy, cz))
        cam.setPosition(QVector3D(cx + span * 1.6, cy + span * 1.2, cz + span * 1.6))

    def reset_camera(self) -> None:
        if self._scene:
            self._frame_camera(self._scene)
