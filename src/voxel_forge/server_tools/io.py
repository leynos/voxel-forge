"""Import, export and editor-launch MCP tools.

Mutable server state is reached through the :mod:`voxel_forge.server` module
object rather than by importing its attributes, so tests that replace
``server.store`` or ``server._sync_bridge`` observe the substitution.
"""

import subprocess  # ruff: ignore[suspicious-subprocess-import]  # typing only; processes are spawned in orchestration
from pathlib import Path

from voxel_forge import bridge, server
from voxel_forge.editor_runtime import EditorRuntimeError, editor_package_root
from voxel_forge.export_roblox import to_luau_merged, write_luau_file
from voxel_forge.mesh_merge import merge_stats
from voxel_forge.orchestration import (
    EditorPorts,
    install_editor_dependencies,
    start_editor_process,
    supervise,
)
from voxel_forge.vox_io import export_obj, export_vox, import_vox

# The supervised editor for this server process, keyed for mutability
# without a global statement.
_editor_state: dict[str, tuple[subprocess.Popen[str], int]] = {}


@server.mcp.tool()
def voxelforge_import_vox(file_path: str) -> str:
    """Import a .vox file in the MagicaVoxel or Goxel export format."""
    scene = import_vox(file_path)
    server.store._scenes[scene.name] = scene
    server.store._current = scene.name
    server._sync_bridge(scene)
    return (
        f"Imported '{file_path}' → scene '{scene.name}' ({scene.block_count()} voxels)"
    )


@server.mcp.tool()
def voxelforge_export_vox(scene_name: str = "", output_path: str = "") -> str:
    """Export to .vox, which Goxel and MagicaVoxel can both open."""
    scene = server.store.get(scene_name or None)
    path = (
        Path(output_path)
        if output_path
        else server._exports_dir() / f"{scene.name}.vox"
    )
    export_vox(scene, path)
    return f"Exported .vox → {path} ({scene.block_count()} voxels)"


@server.mcp.tool()
def voxelforge_merge_stats(scene_name: str = "") -> str:
    """Report how far merging voxels into boxes reduces the part or mesh count.

    Intended as a pre-export check.
    """
    scene = server.store.get(scene_name or None)
    stats = merge_stats(scene)
    return (
        f"Scene '{scene.name}':\n"
        f"  voxels (after de-duplicating overlaps): {stats['voxels']}\n"
        f"  merged boxes (parts): {stats['merged_boxes']}\n"
        f"  reduction: {stats['parts_saved']} ({stats['reduction_percent']}%)"
    )


@server.mcp.tool()
def voxelforge_export_obj(
    scene_name: str = "",
    output_path: str = "",
    merge_boxes: bool = True,  # ruff: ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]  # published MCP tool schema
) -> str:
    """Export to Wavefront .obj.

    With ``merge_boxes=true``, which is recommended, adjacent voxels are
    merged into single boxes.
    """
    scene = server.store.get(scene_name or None)
    if output_path:
        path = Path(output_path)
    else:
        suffix = "_merged" if merge_boxes else ""
        path = server._exports_dir() / f"{scene.name}{suffix}.obj"
    export_obj(scene, path, merge_boxes=merge_boxes)
    stats = merge_stats(scene) if merge_boxes else {"merged_boxes": scene.block_count()}
    parts = stats["merged_boxes"] if merge_boxes else scene.block_count()
    return (
        f"Exported .obj -> {path} ({parts} parts from "
        f"{scene.block_count()} voxels, merge={merge_boxes})"
    )


@server.mcp.tool()
def voxelforge_export_roblox_merged(scene_name: str = "", output_path: str = "") -> str:
    """
    Export Luau for Roblox, merging voxels into large Parts in one Model.

    Merging keeps the part count, and so the lag, down. Run the generated
    code with the Roblox Studio MCP ``execute_luau`` tool in Edit mode.
    """
    scene = server.store.get(scene_name or None)
    stats = merge_stats(scene)
    if output_path:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(to_luau_merged(scene), encoding="utf-8")
    else:
        path = write_luau_file(scene)
    return (
        f"Exported Roblox merged -> {path}\n"
        f"  {stats['voxels']} voxels -> {stats['merged_boxes']} Parts "
        f"({stats['reduction_percent']}% fewer)\n"
        f"  run it in Studio with execute_luau"
    )


@server.mcp.tool()
def voxelforge_export_obj_legacy(scene_name: str = "", output_path: str = "") -> str:
    """Export to Wavefront .obj without merging, as Goxel supports."""
    scene = server.store.get(scene_name or None)
    path = (
        Path(output_path)
        if output_path
        else server._exports_dir() / f"{scene.name}.obj"
    )
    export_obj(scene, path, merge_boxes=False)
    return f"Exported .obj (no merge) -> {path} ({scene.block_count()} voxels)"


def _running_editor() -> tuple[subprocess.Popen[str], int] | None:
    """Return the supervised editor process and port when still alive."""
    editor = _editor_state.get("editor")
    if editor is not None and editor[0].poll() is None:
        return editor
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
    _editor_state["editor"] = editor
    return editor


@server.mcp.tool()
def voxelforge_launch_editor() -> str:
    """
    Open the VoxelForge web editor in a browser, with a Three.js 3D view.

    The bridge synchronises automatically over WebSocket, so edits can be
    made either in the editor or through MCP.
    """
    server._ensure_bridge()
    bridge_ports = bridge.current_ports()
    if bridge_ports is None:
        return "The bridge is not ready yet — call voxelforge_launch_editor again"
    editor = _running_editor()
    if editor is None:
        try:
            editor = _start_supervised_editor(bridge_ports)
        except EditorRuntimeError as exc:
            return (
                f"The editor could not be opened: {exc}\n"
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
