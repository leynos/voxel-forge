# VoxelForge users guide

VoxelForge is a voxel editor inspired by
[Goxel](https://github.com/guillaumechereau/goxel) with an MCP bridge, so AI
clients such as Cursor and Claude Desktop can create and edit 3D models
directly. This guide covers installation and everyday use. Contributors
changing the code rather than driving the tool should read the
[developers guide](developers-guide.md).

## Installing

VoxelForge installs as a standard Python tool on Linux, macOS, and Windows,
and the command is the same on all three. The recommended route is
[uv](https://docs.astral.sh/uv/):

```bash
uv tool install git+https://github.com/leynos/voxel-forge
```

This puts the three commands listed under
[installed commands](#installed-commands) on the `PATH`. VoxelForge is MIT
licensed.

### The desktop app

The desktop application is an optional extra, because it depends on the Qt
bindings in PySide6. Install it with:

```bash
uv tool install \
  'voxel-forge[desktop] @ git+https://github.com/leynos/voxel-forge'
```

The extra installs `PySide6>=6.6.0` and `pyinstaller>=6.0`.

`uv tool install` performs a fresh dependency resolution and does not read the
repository lockfile. A fresh install is therefore governed by the version
bounds declared in `pyproject.toml`, not by the pins in `uv.lock`.

### Working from a checkout

Holding the source is an alternative to installing the tool, and it is the
only way to run the web editor:

```bash
git clone https://github.com/leynos/voxel-forge
cd voxel-forge
uv sync
uv run voxel-forge-mcp
```

Add `--extra desktop` to `uv sync` to work on the desktop application, then
run `uv run voxel-forge`.

## Installed commands

| Command | What it does |
| --- | --- |
| `voxel-forge-mcp` | MCP server over stdio (primary interface) |
| `voxel-forge-bridge` | Standalone WebSocket/HTTP bridge for the editor |
| `voxel-forge` | Native desktop app (requires the `desktop` extra) |

Running `voxel-forge-mcp` with no arguments starts the MCP server on stdio and
blocks. That is what an MCP client expects.

`voxel-forge-mcp --help` (or `-h`) prints usage and exits with status 0
without starting the bridge or binding a socket, so it is a safe way to check
that the command is on the `PATH`.

`voxel-forge-bridge` runs the bridge on its own rather than under an MCP
client. It announces the ports it has bound on standard error, because
standard output is reserved for MCP protocol data.

## Connecting an MCP client

Point the client at the installed `voxel-forge-mcp` command with an empty
argument list:

```json
{"command": "voxel-forge-mcp", "args": []}
```

Cursor reads this from `~/.cursor/mcp.json` under the name `VoxelForge`, and
Claude Desktop has its own configuration file. The
[README](../README.md#connecting-an-mcp-client) carries the full example for
each client.

After changing the configuration, restart the client and confirm that
VoxelForge shows as connected.

## The web editor

The web editor is a Three.js application in the `editor` directory of a
checkout. It requires Node.js; continuous integration builds it with Node 22.
From the checkout root:

```bash
cd editor
npm install
npm run dev
```

Then open `http://localhost:5173`. The MCP tool `voxelforge_launch_editor`
directs callers to this portable invocation on every platform, rather than to
a platform-specific wrapper.

The editor talks to the bridge over WebSocket at `ws://127.0.0.1:8765`, and
the bridge serves the current scene as JSON at
`http://127.0.0.1:8766/scene`. Both ports are bound to the loopback address
`127.0.0.1`, so they are reachable only from the same machine.

The editor is a source-checkout component. It is not yet packaged into the
installed tool.

## Where scenes and exports live

- Scenes: `~/.voxel-forge/scenes/`
- Exports: `~/.voxel-forge/exports/`
- On Windows the same directories are
  `%USERPROFILE%\.voxel-forge\scenes\` and
  `%USERPROFILE%\.voxel-forge\exports\`.

Scene names are validated before they are used as filenames, so a scene name
cannot escape the scene directory.

The desktop application opens scenes from the same directory that the MCP
server saves them to, so a scene created through an AI client can be opened
there afterwards.

## Python export helpers

Python integrations can call the OBJ and merged Roblox Luau export helpers
directly. Given a scene and destination path, optional settings are
keyword-only:

```python
from voxel_forge.export_roblox import to_luau_merged
from voxel_forge.vox_io import export_obj

obj_path = export_obj(scene, path, merge_boxes=False)
luau_source = to_luau_merged(scene, parent="workspace", anchor=False)
```

The MCP tools, including `voxelforge_export_obj`, are unchanged. Integrations
upgrading from positional optional arguments should follow the
[0.3 migration guide](migration-0.3.md).

## Windows batch wrappers

Four batch files are provided for Windows: `run-mcp.bat`, `run-desktop.bat`,
`run-editor.bat`, and `build-desktop.bat`. They are conveniences for a
checkout, and they are Windows-only; on Linux or macOS, use the commands in
this guide instead.

`run-mcp.bat` calls the installed entry point through
`uv run voxel-forge-mcp`, so it does not run the files under `src/` directly.

## For contributors

The [developers guide](developers-guide.md) records the console-script entry
points, the desktop launcher boundary, the toolchain requirements, and the
verification gates a change must pass.

Upgrading an existing 0.1.x installation is covered by
[migrating to 0.2](migration-0.2.md).

The [0.3 migration guide](migration-0.3.md) records the Python export API and
persisted-scene type changes for that release.
