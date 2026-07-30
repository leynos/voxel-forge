# VoxelForge

**VoxelForge** is a voxel editor with an **MCP bridge**, so AI assistants
(Cursor, Claude Desktop and others) can create and edit 3D models
directly.

ภาษาไทย: [README.th.md](README.th.md)

> **Provenance.** This repository, `leynos/voxel-forge`, is a soft fork of
> [thanakon228/voxel-forge](https://github.com/thanakon228/voxel-forge) —
> the original VoxelForge by thanakon228. VoxelForge is inspired by
> [Goxel](https://github.com/guillaumechereau/goxel) (GPL-3.0) but is an
> independent, MCP-first implementation: it does not fork Goxel's C code,
> and the two projects share only the interchangeable `.vox` and `.obj`
> formats. See [docs/provenance.md](docs/provenance.md) and
> [docs/fork-and-interface-boundary.md](docs/fork-and-interface-boundary.md)
> for detail.

## Features

| Feature | Detail |
| --- | --- |
| 24-bit RGB | Full colour palette |
| Layers | Multiple layers, as in Goxel |
| Export | `.vox` (MagicaVoxel), `.obj` (Wavefront) |
| Import | `.vox` from Goxel or MagicaVoxel |
| Web editor | Three.js 3D view — click to place or remove voxels |
| MCP | Connects Cursor, Claude and other clients |

## Installation

VoxelForge installs as a standard Python tool on Linux, macOS, and Windows.
The recommended route is [uv](https://docs.astral.sh/uv/):

```bash
uv tool install git+https://github.com/leynos/voxel-forge
```

This puts three console scripts on your `PATH`:

| Command | Purpose |
| --- | --- |
| `voxel-forge-mcp` | MCP server over stdio (primary interface) |
| `voxel-forge-bridge` | Standalone WebSocket/HTTP bridge for the web editor |
| `voxel-forge` | Native desktop app (requires the `desktop` extra) |

For the desktop app, install with the extra:

```bash
uv tool install 'voxel-forge[desktop] @ git+https://github.com/leynos/voxel-forge'
```

Working from a checkout instead:

```bash
git clone https://github.com/leynos/voxel-forge
cd voxel-forge
uv sync            # add --extra desktop for the desktop app
uv run voxel-forge-mcp
```

## Connecting an MCP client

Point your client at the installed `voxel-forge-mcp` command.

### Cursor (`~/.cursor/mcp.json`)

```json
"VoxelForge": {
  "command": "voxel-forge-mcp",
  "args": []
}
```

### Claude Desktop

```json
{
  "mcpServers": {
    "VoxelForge": {
      "command": "voxel-forge-mcp",
      "args": []
    }
  }
}
```

On Windows, the `run-mcp.bat` wrapper remains available for convenience from
a checkout; it invokes the same installed entry point via
`uv run voxel-forge-mcp` rather than running files in `src/` directly.

Restart the client and check its MCP panel shows `VoxelForge` as connected.

### Headless operation

By default the server binds no socket: the editor bridge starts only when
`voxelforge_launch_editor` is called. To start the bridge listener eagerly,
run `voxel-forge-mcp --bridge` or set `VOXELFORGE_BRIDGE=1`. This makes the
server safe for headless and sandboxed environments such as continuous
integration.

## Desktop app (no browser required)

### Running

After installing with the `desktop` extra (see [Installation](#installation)):

```bash
voxel-forge
```

Or from a checkout after `uv sync --extra desktop`:

```bash
uv run voxel-forge
```

On Windows, `run-desktop.bat` wraps the same command.

### Building an .exe (Windows)

```powershell
.\build-desktop.bat
```

The result is `dist\VoxelForge\VoxelForge.exe` — double-click it to run,
with no Python installation and no browser needed.

### Desktop features

- Open and save scenes (JSON)
- Import `.vox`; export `.obj` (merged), `.vox`, and Roblox Luau
- Create → Build Tree (resolution 1–8)
- Native 3D view (Qt3D) — orbit the camera with the middle mouse button

The MCP server for AI use stays separate (`run-mcp.bat` on Windows): build a
scene through an AI assistant, then open it in the desktop app from
`~/.voxel-forge/scenes/` (on Windows,
`%USERPROFILE%\.voxel-forge\scenes\`).

## Web editor (optional)

The editor is served by [Bun](https://bun.sh) and ships inside the installed
wheel, so `voxelforge_launch_editor` starts it without a checkout. The MCP
server supervises that Bun process. The editor binds an **ephemeral** port
and reports it as a structured `listening` event on stdout, so
`voxelforge_launch_editor` can return the resulting URL and open it in a
browser.

To run the editor by hand from a checkout:

```bash
cd editor
bun install
bun run dev
```

On Windows, `run-editor.bat` wraps the same commands. The standalone dev
server also binds an ephemeral port by default; set
`VOXELFORGE_EDITOR_PORT=5173` to use the port that the bridge keeps
pre-registered as an allowed origin for this flow.

The editor synchronizes in both directions with MCP over WebSocket:
creating or editing a scene through MCP pushes it to the browser, and
placing or removing a voxel in the editor updates the scene on the MCP
side. The bridge binds ephemeral WebSocket and HTTP ports too, and
`voxelforge_launch_editor` reports both. Only the standalone
`voxel-forge-bridge` command defaults to the fixed ports 8765 (WebSocket)
and 8766 (HTTP); both accept `--ws-port` and `--http-port`.

Both the editor and the bridge bind loopback (`127.0.0.1`), so they are
reachable from this machine only and are never exposed to other machines on
the network.

### Building through an AI assistant

An example prompt:

> Build a Goxel-style voxel house called my_house — an 8x8 grey base, a
> 6x6x4 white body, and a red triangular roof.

The assistant then calls:

1. `voxelforge_create_scene`
2. `voxelforge_fill_box` / `voxelforge_place_many`
3. `voxelforge_preview` to check the shape
4. `voxelforge_export_vox` or `voxelforge_export_obj`

`voxelforge_fill_box` and `voxelforge_place_many` are limited to
**100,000 voxels per call**. Split anything larger across several calls.

### Opening the result in Goxel

Export `.vox`, then open it in Goxel or MagicaVoxel:

```text
~/.voxel-forge/exports/my_house.vox
```

## Core MCP tools

| Tool | Purpose |
| --- | --- |
| `voxelforge_about` | Project information |
| `voxelforge_create_scene` | Create a new scene |
| `voxelforge_place_many` | Place voxels from JSON |
| `voxelforge_fill_box` | Fill a 3D box |
| `voxelforge_add_layer` | Add a layer |
| `voxelforge_preview` | Show an ASCII preview |
| `voxelforge_export_vox` | Export `.vox` |
| `voxelforge_export_obj` | Export `.obj` |
| `voxelforge_import_vox` | Import `.vox` |
| `voxelforge_launch_editor` | Open the web editor |
| `voxelforge_save` / `voxelforge_load` | Save and load a scene |

## Data folders

- Scenes: `~/.voxel-forge/scenes/`
- Exports: `~/.voxel-forge/exports/`

## Architecture

```text
┌─────────────┐   stdio/MCP   ┌──────────────┐  WebSocket   ┌─────────────┐
│ Cursor AI   │ ◄───────────► │ MCP Server   │ ◄──────────► │ Web Editor  │
│ Claude etc. │               │ (Python)     │              │ (Three.js)  │
└─────────────┘               └──────────────┘              └─────────────┘
```

## Compared with cube-world-voxel-mcp

| | VoxelForge | cube-world-voxel-mcp |
| --- | --- | --- |
| Purpose | General Goxel-style editor | Roblox Cube World |
| Voxel size | 1×1×1 | 2×2×2 studs |
| GUI | Three.js editor | None (headless) |
| Export | `.vox`, `.obj` | Luau → Roblox |

The two are complementary, and Cursor can use both MCP servers at once.

## Licence

MIT — see [LICENSE](LICENSE), copyright thanakon228. Goxel itself is
GPL-3.0 ([the Goxel project](https://github.com/guillaumechereau/goxel));
none of its code is used here.
