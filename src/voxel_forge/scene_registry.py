"""Lock-owning in-memory registry shared by MCP and the editor bridge."""

from __future__ import annotations

import threading

from .model_scene import VoxelScene
from .model_validation import (
    NoCurrentSceneError,
    UnknownSceneError,
    validate_scene_name,
)


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
        Re-entrant lock guarding scene reads and mutations.

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
        NoCurrentSceneError
            If ``name`` is empty and no scene is current.
        UnknownSceneError
            If ``name`` is given and is not registered in this session.

        Both derive from ``KeyError``, so a caller that only needs "there is no
        scene" can keep catching that.
        """
        with self._lock:
            key = name or self._current
            if not key:
                raise NoCurrentSceneError
            if key not in self._scenes:
                # A named lookup that misses is a different failure from having
                # no current scene, which is why it is a different exception
                # type. The two need different remedies -- create a scene,
                # versus load the saved one or correct the name -- and the
                # adapter is what decides how to word that.
                raise UnknownSceneError(key)
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
        UnknownSceneError
            If the name is not registered. A selection target is always named,
            so this is the same failure as a named ``get`` miss and reuses its
            type. Loading from disk is the caller's responsibility, so this
            registry stays free of file I/O.
        """
        with self._lock:
            if name not in self._scenes:
                raise UnknownSceneError(name)
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
