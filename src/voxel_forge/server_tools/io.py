"""Io MCP tools using the shared lock-owning server registry."""

from __future__ import annotations

import json
import logging
import threading
import typing as typ
from pathlib import Path

if typ.TYPE_CHECKING:
    import subprocess

from voxel_forge import bridge, server
from voxel_forge.editor_runtime import EditorRuntimeError, editor_package_root
from voxel_forge.orchestration import (
    EditorPorts,
    install_editor_dependencies,
    start_editor_process,
    stop_editor_process,
    supervise,
)

_LOG = logging.getLogger(__name__)

# The supervised editor for this server process, keyed for mutability
# without a global statement.
_editor_state: dict[str, tuple[subprocess.Popen[str], int, tuple[int, int]]] = {}
_editor_lock = threading.Lock()


@server.mcp.tool()
def voxelforge_save(scene_name: str = "") -> str:
    """Save a scene to ~/.voxel-forge/scenes/.

    Parameters
    ----------
    scene_name : str, optional
        Name of the target scene; defaults to the current scene.

    Returns
    -------
    str
        A confirmation message with the path the file was saved to.

    Raises
    ------
    KeyError
        If the target scene is not found.
    ValueError
        If the scene name is not safe to use as a filename.
    OSError
        If writing the folder or file fails.
    """
    with server.store.lock:
        scene = server.store.get(scene_name or None)
        path = server.save_scene(scene)
        return f"Saved '{scene.name}' to {path}"


@server.mcp.tool()
def voxelforge_load(name: str) -> str:
    """Load a scene from a file.

    Parameters
    ----------
    name : str
        Name of the saved scene, without the ``.json`` suffix.

    Returns
    -------
    str
        A confirmation message with the block count.

    Raises
    ------
    FileNotFoundError
        If no scene file with this name is found.
    ValueError
        If the name is unsafe, or the file contents fail validation.
    OSError
        If reading the file fails.
    """
    scene = server.load_scene(name)
    with server.store.lock:
        server.store.register(scene)
        server._sync_bridge(scene)
        return f"Loaded '{name}' ({scene.block_count()} blocks)"


@server.mcp.tool()
def voxelforge_list_scenes() -> str:
    """List the scenes in this session and the scenes saved to disk.

    Returns
    -------
    str
        JSON holding ``active_session`` (in-memory scenes) and
        ``saved_on_disk`` (files in ``~/.voxel-forge/scenes``).

    Raises
    ------
    OSError
        If the scene folder cannot be read; a read failure is not swallowed
        into an empty listing.
    """
    with server.store.lock:
        active = server.store.list_active()
    return json.dumps(
        {"active_session": active, "saved_on_disk": server.list_saved_scenes()},
        ensure_ascii=False,
        indent=2,
    )


@server.mcp.tool()
def voxelforge_import_vox(file_path: str) -> str:
    """Import a .vox file (the MagicaVoxel / Goxel export format).

    Parameters
    ----------
    file_path : str
        Path to the ``.vox`` file.

    Returns
    -------
    str
        A confirmation message with the resulting scene name and voxel count.

    Raises
    ------
    ValueError
        If the file is not a valid ``.vox`` document.
    OSError
        If reading the file fails.
    """
    scene = server.import_vox(file_path)
    with server.store.lock:
        server.store.register(scene)
        server._sync_bridge(scene)
        voxels = scene.block_count()
        return f"import '{file_path}' → scene '{scene.name}' ({voxels} voxels)"


@server.mcp.tool()
def voxelforge_export_vox(scene_name: str = "", output_path: str = "") -> str:
    """Export to .vox (opens in Goxel / MagicaVoxel).

    Parameters
    ----------
    scene_name : str, optional
        Name of the target scene; defaults to the current scene.
    output_path : str, optional
        Destination file path; defaults to
        ``~/.voxel-forge/exports/<name>.vox``.

    Returns
    -------
    str
        A confirmation message with the file path and voxel count.

    Raises
    ------
    ValueError
        If the scene exceeds 256 cells per axis, carries more than 255
        colours, or has voxels that overlap between visible layers.
    KeyError
        If the target scene is not found.
    OSError
        If writing the file fails.
    """
    with server.store.lock:
        scene = server.store.get(scene_name or None)
        path = server._export_path(scene, output_path, ".vox")
        server.export_vox(scene, path)
        return f"export .vox → {path} ({scene.block_count()} voxels)"


@server.mcp.tool()
def voxelforge_export_obj(
    scene_name: str = "",
    output_path: str = "",
    merge_boxes: bool = True,  # ruff: ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]  # MCP schema
) -> str:
    """Export to Wavefront .obj — merge_boxes=true merges adjacent voxels (recommended).

    Parameters
    ----------
    scene_name : str, optional
        Name of the target scene; defaults to the current scene.
    output_path : str, optional
        Destination file path; defaults to ``~/.voxel-forge/exports/``.
    merge_boxes : bool, optional
        Merge adjacent voxels into larger boxes; defaults to ``True``.

    Returns
    -------
    str
        A confirmation message with the path, part count and voxel count.

    Raises
    ------
    KeyError
        If the target scene is not found.
    OSError
        If writing the file fails.
    """
    with server.store.lock:
        scene = server.store.get(scene_name or None)
        suffix = "_merged.obj" if merge_boxes else ".obj"
        path = server._export_path(scene, output_path, suffix)
        server.export_obj(scene, path, merge_boxes=merge_boxes)
        stats = (
            server.merge_stats(scene)
            if merge_boxes
            else {"merged_boxes": scene.block_count()}
        )
        parts = stats["merged_boxes"] if merge_boxes else scene.block_count()
        return (
            "export .obj -> "
            f"{path}"
            " ("
            f"{parts}"
            " parts from "
            f"{scene.block_count()}"
            " voxels, merge="
            f"{merge_boxes}"
            ")"
        )


@server.mcp.tool()
def voxelforge_export_obj_legacy(scene_name: str = "", output_path: str = "") -> str:
    """Export to Wavefront .obj (as supported by Goxel).

    Parameters
    ----------
    scene_name : str, optional
        Name of the target scene; defaults to the current scene.
    output_path : str, optional
        Destination file path; defaults to ``~/.voxel-forge/exports/``.

    Returns
    -------
    str
        A confirmation message with the path and voxel count.

    Raises
    ------
    KeyError
        If the target scene is not found.
    OSError
        If writing the file fails.
    """
    with server.store.lock:
        scene = server.store.get(scene_name or None)
        path = server._export_path(scene, output_path, ".obj")
        server.export_obj(scene, path, merge_boxes=False)
        return f"export .obj (no merge) -> {path} ({scene.block_count()} voxels)"


@server.mcp.tool()
def voxelforge_export_roblox_merged(scene_name: str = "", output_path: str = "") -> str:
    """Export Luau for Roblox — merges voxels into large Parts in one Model.

    Run the resulting code in Roblox Studio via the Roblox_Studio MCP
    ``execute_luau`` tool (Edit mode).
    """
    with server.store.lock:
        scene = server.store.get(scene_name or None)
        stats = server.merge_stats(scene)
        if output_path:
            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(server.to_luau_merged(scene), encoding="utf-8")
        else:
            path = server.write_luau_file(scene)
        return (
            f"export Roblox merged -> {path}\n"
            f"  {stats['voxels']} voxels -> {stats['merged_boxes']} Parts "
            f"({stats['reduction_percent']}% reduction)\n"
            f"  run it in Studio with execute_luau"
        )


def _running_editor() -> tuple[subprocess.Popen[str], int] | None:
    """Return the current editor, retiring stale processes and origin allowances."""
    editor = _editor_state.get("editor")
    if editor is None:
        return None
    process, port, configured_ports = editor
    status = process.poll()
    if status is None and configured_ports == bridge.current_ports():
        return process, port
    bridge.unregister_editor_origin(port)
    if status is None:
        _LOG.info("Restarting editor pid=%d after bridge endpoint change", process.pid)
        stop_editor_process(process)
    else:
        _LOG.warning(
            "Editor exited unexpectedly pid=%d status=%d; restarting",
            process.pid,
            status,
        )
    _editor_state.pop("editor", None)
    return None


def _start_supervised_editor(
    bridge_ports: tuple[int, int],
) -> tuple[subprocess.Popen[str], int]:
    """Start the bundled editor under supervision and remember it.

    The editor's discovered port is registered as an allowed bridge
    origin, so the origin check follows the dynamically allocated port
    rather than a constant.
    """
    root = editor_package_root()
    if not (root / "node_modules").is_dir():
        install_editor_dependencies()
    ws_port, http_port = bridge_ports
    ports = EditorPorts(bridge_ws=ws_port, bridge_http=http_port)
    process, port = start_editor_process(ports)
    supervise(process)
    bridge.register_editor_origin(port)
    editor = (process, port)
    _editor_state["editor"] = (process, port, bridge_ports)
    return editor


@server.mcp.tool()
def voxelforge_launch_editor() -> str:
    """
    Open the VoxelForge web editor in the browser (Three.js 3D view).

    The bridge syncs automatically over WebSocket — edits made in the editor
    and edits made through MCP both propagate.
    """
    with _editor_lock:
        server._ensure_bridge("launch_editor")
        bridge_ports = bridge.current_ports()
        if bridge_ports is None:
            return "Bridge is not ready — call voxelforge_launch_editor again"
        editor = _running_editor()
        if editor is None:
            try:
                editor = _start_supervised_editor(bridge_ports)
            except EditorRuntimeError as exc:
                return (
                    f"Could not open the editor: {exc}\n"
                    "Install Bun (https://bun.sh), then call "
                    "voxelforge_launch_editor again"
                )
    _, port = editor
    ws_port, http_port = bridge_ports
    url = f"http://127.0.0.1:{port}"

    import webbrowser

    webbrowser.open(url)
    return (
        f"Opened {url} (Bun editor supervised by the server)\n"
        f"Bridge: ws://127.0.0.1:{ws_port} | "
        f"HTTP scene: http://127.0.0.1:{http_port}/scene"
    )
