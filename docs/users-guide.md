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

Holding the source is an alternative to installing the tool. The installed
wheel also includes the web editor runtime.

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

### Headless operation

The server binds no socket unless a bridge is requested, so it is safe to run
headless, in a sandbox, or in continuous integration, where there is no
display, browser, or editor.

The bridge starts only when something wants it:

- Eagerly, with `voxel-forge-mcp --bridge` or `VOXELFORGE_BRIDGE=1`. The
  listener starts before the server serves stdio.
- On demand, when an MCP client calls the `voxelforge_launch_editor` tool.

Editing a scene notifies a bridge that is already running, but never starts
one, so an edit-only session stays headless however many edits it makes.

```bash
# Start the server with the bridge already listening.
voxel-forge-mcp --bridge
```

The server reports the mode it started in on standard error, with the fields
`operation=server_start`, `bridge_mode=headless` or `bridge_mode=eager`, and
`bridge_state=down` or `bridge_state=running`. Standard output stays reserved
for MCP protocol data.

When the bridge comes up it says so once, naming what asked for it
(`trigger=server_start` for the eager path, `trigger=launch_editor` for the
on-demand one), and when it stops it reports the transition:

```text
VoxelForge server: operation=bridge_start trigger=launch_editor
VoxelForge bridge: operation=bridge_state bridge_state=down error_category=CancelledError
```

`error_category` names the class of whatever ended the listeners; an ordinary
shutdown cancels the task, so it reports `CancelledError`. Calling
`voxelforge_launch_editor` again while the bridge is already up does not report
another start, so the line counts transitions rather than calls.

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

### What the tools say back

**Every confirmation is a short English sentence** describing what the tool
did, because that sentence is what a language model reads to decide its next
call. A confirmation names the scene or the parameters it acted on and the
resulting counts, so a caller can tell a successful edit from a no-op without
a second call:

```text
create_scene   -> Created scene 'house' (initial layer: Layer 1)
place_block    -> placed (0,0,0) colour '2' — 1 blocks total
fill_box       -> filled 2 voxels with colour '3' — 3 blocks total
place_many     -> placed 1 voxels in 'house' — 4 blocks total
add_layer      -> Added layer 'top' to 'house' — 2 layers in total
select_scene   -> Selected scene 'house' (4 blocks)
save           -> Saved 'house' to ~/.voxel-forge/scenes/house.json
load           -> Loaded 'house' (4 blocks)
```

Removing a voxel reports which outcome occurred, since both calls succeed:

```text
remove_block (occupied)   -> removed
remove_block (empty)      -> no voxel there
```

**A few tools answer with a document instead**, and a client should parse
those rather than read them as prose. Three shapes occur:

- **JSON**, from three tools, each with its own contract:
  - `voxelforge_list_scenes` returns an object with `active_session` (scenes
    in this session) and `saved_on_disk` (files in the scene directory).
  - `voxelforge_get_info` returns the scene itself, matching
    `VoxelScene.to_dict()`: `name`, `voxel_size`, `palette`, `active_layer`,
    and `layers`.
  - `voxelforge_default_palette` returns a colour mapping, from palette keys
    to `[r, g, b]` arrays.
- **An ASCII preview**, from `voxelforge_preview`: a summary line followed by
  one rendering per Y slice, for checking a shape without rendering it.
- **Multi-line statistics or status**, from `voxelforge_merge_stats` and the
  editor tools. These are several labelled lines rather than one sentence.

The short-sentence claim above is about confirmations, not about every
return value. Treating it as universal is the mistake this section exists to
prevent: a client that assumes one line per call will misread the JSON and
the preview.

The limits are stated in the messages that enforce them. `fill_box` and
`place_many` are each capped at **100,000 voxels per call**, and a bulk JSON
payload is capped at **8,000,000 characters**. Exceeding either is rejected
before any mutation, so a rejected call leaves the scene untouched.

Error messages are written as the recovery instruction, not just as a
diagnosis. A scene name that is not loaded says which name was missing and
names both ways to get one:

```text
no scene yet — call voxelforge_create_scene first
scene 'absent' is not loaded in this session — call voxelforge_load for a
saved scene, or use the name of an existing session scene
```

The first is for a session with no scene at all; the second is for a session
that has scenes but not one by that name. They are different failures with
different remedies, which is why they do not share one message.

## The web editor

The Three.js editor is bundled in the installed wheel and served by Bun. Bun
must be installed on the host. Call `voxelforge_launch_editor` from the MCP
client to start the supervised editor and open it in the browser.

For manual development from a checkout, run:

```bash
cd editor
bun install
bun run dev
```

Then open `http://127.0.0.1:5173`. This standalone command uses port 5173.
The supervised MCP launch chooses an available editor port, opens the page,
and reports the actual URL. The standalone bridge defaults to WebSocket port
8765 and HTTP port 8766; the MCP server chooses available bridge ports and
passes their values to the editor.

Both the editor and bridge bind to loopback (`127.0.0.1`), so they are
reachable only from the same machine. Loopback binding limits network access;
it is not authentication. The bridge checks browser WebSocket `Origin`
headers against the editor origins it has registered. Connections without an
`Origin` header are allowed for non-browser clients, so local access should
not be treated as a security boundary between users or processes on the same
machine.

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

These helpers are a supported in-process API: install `voxel-forge` and import
them by name, as above. That is a versioned dependency on a released package,
which is a different thing from the cross-project code boundary the
[fork and interface boundary](fork-and-interface-boundary.md) describes — that
boundary is about not vendoring VoxelForge source and not co-owning shared
types, and importing the installed package is allowed. When the interface is a
file or a command rather than a Python call, that document is the one to read.

The MCP tool names and their request schemas are unchanged, so an integration
that calls `voxelforge_export_obj` by name keeps working. What a call says
*back* did change: confirmations, JSON payloads, and error messages are now
English prose with the shapes described under
[What the tools say back](#what-the-tools-say-back), and a scene-lookup
failure now names the recovery step to take. An integration that reads the
response text rather than only checking for success should follow the
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
