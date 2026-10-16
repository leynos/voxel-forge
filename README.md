# VoxelForge

**VoxelForge** is our voxel editor, built on the ideas of
[Goxel](https://github.com/guillaumechereau/goxel), with an **MCP bridge** that
lets AI clients (Cursor, Claude Desktop, and others) create and edit 3D models
directly.

> VoxelForge is a soft fork of
> [`thanakon228/voxel-forge`](https://github.com/thanakon228/voxel-forge),
> which is MIT-licensed, as this repository is.
>
> It is **not** a fork of Goxel. Goxel's own implementation is GPL-3.0, while
> VoxelForge is an independent, MCP-first implementation that carries no Goxel
> C source. The two interoperate through the file formats they both read and
> write: `.vox` (MagicaVoxel) and `.obj` (Wavefront).
>
> [`docs/provenance.md`](docs/provenance.md) records the evidence behind those
> claims, and
> [`docs/fork-and-interface-boundary.md`](docs/fork-and-interface-boundary.md)
> states what the boundary means for anyone consuming the project.

## Features

| Feature | Detail |
| --- | --- |
| 24-bit RGB | Full colour palette |
| Layers | Multiple layers, as in Goxel |
| Export | `.vox` (MagicaVoxel), `.obj` (Wavefront) |
| Import | `.vox` from Goxel / MagicaVoxel |
| Web Editor | Three.js 3D — click to place or delete voxels |
| MCP | Connects Cursor, Claude, and other clients |

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

You can run the same command the client runs, to test it from a terminal:

```bash
voxel-forge-mcp
```

This invokes the installed console script, so it fails the same way the client
would if the tool is not on `PATH`. From a checkout, `uv run voxel-forge-mcp`
exercises the project environment instead.

Restart the client and check its MCP panel shows `VoxelForge` as connected.

### Headless operation

By default the server binds no socket: the editor bridge starts only when
`voxelforge_launch_editor` is called. To start the bridge listener eagerly,
run `voxel-forge-mcp --bridge` or set `VOXELFORGE_BRIDGE=1`. This makes the
server safe for headless and sandboxed environments such as continuous
integration.

## Desktop App (no browser)

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

The result lands in `dist\VoxelForge\VoxelForge.exe` — double-click to launch
it, with no Python and no browser required.

### Desktop features

- Open and save scenes (JSON)
- Import `.vox` / export `.obj` (merged), `.vox`, and Roblox Luau
- Create → Build Tree (resolution 1–8)
- Native 3D view (Qt3D) — orbit the camera with the middle mouse button

The AI-facing MCP server is still a separate process (`voxel-forge-mcp`):
build a scene through AI, then open it in the Desktop app from
`~/.voxel-forge/scenes/` (Windows: `%USERPROFILE%\.voxel-forge\scenes\`).

---

## Web Editor (alternative)

```bash
cd editor
bun install
bun run dev
```

The editor is served by [Bun](https://bun.sh) and is bundled inside the
installed wheel, so `voxelforge_launch_editor` works without a checkout.
On Windows, `run-editor.bat` wraps the same commands.

Calling `voxelforge_launch_editor` from an MCP client opens the editor and
reports the URL it actually bound. For manual development the commands above
serve the editor on `http://127.0.0.1:5173`, and the standalone bridge uses
WebSocket `ws://127.0.0.1:8765` by default; a call made through MCP picks a
free port instead and passes it to the editor automatically. Scenes created or
edited over MCP are pushed to the browser, and voxels placed or deleted in the
editor update the MCP-side scene.

Both the web editor and the bridge bind to loopback (`127.0.0.1`), so they are
reachable only from this machine and are not exposed to other hosts on the
network.

### 2. Creating a model with AI

An example prompt:

> Build a Goxel-style voxel house called my_house — an 8x8 grey base, a 6x6x4
> white body, and a red triangular roof

The AI then calls:

1. `voxelforge_create_scene`
2. `voxelforge_fill_box` / `voxelforge_place_many`
3. `voxelforge_preview` to check the shape
4. `voxelforge_export_vox` or `voxelforge_export_obj`

`voxelforge_fill_box` and `voxelforge_place_many` are each capped at **100,000
voxels per call**. Split a larger scene across several calls.

### 3. Opening the result in Goxel

Export `.vox`, then open it in Goxel or MagicaVoxel:

```text
~/.voxel-forge/exports/my_house.vox
```

On Windows that path is
`%USERPROFILE%\.voxel-forge\exports\my_house.vox`.

## Main MCP tools

| Tool | Purpose |
| --- | --- |
| `voxelforge_about` | Project information |
| `voxelforge_create_scene` | Create a new scene |
| `voxelforge_place_many` | Place voxels from JSON |
| `voxelforge_fill_box` | Fill a 3D box |
| `voxelforge_add_layer` | Add a layer |
| `voxelforge_preview` | View an ASCII preview |
| `voxelforge_export_vox` | Export `.vox` |
| `voxelforge_export_obj` | Export `.obj` |
| `voxelforge_import_vox` | Import `.vox` |
| `voxelforge_launch_editor` | Open the web editor |
| `voxelforge_save` / `voxelforge_load` | Save/load a scene |

## Data directories

- Scenes: `~/.voxel-forge/scenes/`
- Exports: `~/.voxel-forge/exports/`

## Architecture

```text
┌─────────────┐   stdio/MCP   ┌──────────────┐  WebSocket   ┌─────────────┐
│ Cursor AI   │ ◄───────────► │ MCP Server   │ ◄──────────► │ Web Editor  │
│ Claude etc. │               │ (Python)     │              │ (Three.js)  │
└─────────────┘               └──────────────┘              └─────────────┘
```

## Comparison with cube-world-voxel-mcp

| | VoxelForge | cube-world-voxel-mcp |
| --- | --- | --- |
| Purpose | General Goxel-style editor | Roblox Cube World |
| Voxel size | 1×1×1 | 2×2×2 studs |
| GUI | Three.js editor | None (headless) |
| Export | .vox, .obj | Luau → Roblox |

The two can be used side by side as MCP servers in the same Cursor session.

## Documentation

- [Users guide](docs/users-guide.md) — installation, the three commands, the
  MCP client setup, the web editor, and where scenes and exports are stored.
- [Developers guide](docs/developers-guide.md) — entry points, the desktop
  launcher boundary, dependency and toolchain requirements, and the
  verification gates.
- [Fork and interface boundary](docs/fork-and-interface-boundary.md) — what the
  fork guarantees, and the file-format and command-line contract consumers may
  rely on.
- [Provenance](docs/provenance.md) — the upstream project, the licence
  position, and the evidence that VoxelForge carries no Goxel C source.
- [Migrating to 0.2](docs/migration-0.2.md) — the installed-command changes in
  this release and what an existing setup has to update.
- [Migrating to 0.3](docs/migration-0.3.md) — Python export arguments and
  persisted-scene type changes planned for that release.

The long-term direction of the project is recorded in the
[roadmap](docs/roadmap.md).

## License

MIT — VoxelForge code belongs to its authors.

Original Goxel: GPL-3.0
([Goxel project](https://github.com/guillaumechereau/goxel))
