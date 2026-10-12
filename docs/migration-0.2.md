# Migrating to VoxelForge 0.2

Version 0.2 makes VoxelForge installable as a tool, so an MCP client can be
pointed at a command rather than at a checkout. The installed surface changed
in ways that affect an existing setup, and this document records what to change
and why. It covers the move from 0.1.x to 0.2.0 and nothing later.

The [users guide](users-guide.md) describes the resulting behaviour; this
document is only about the transition.

## Summary of the breaking changes

| Area | In 0.1.x | In 0.2 |
| --- | --- | --- |
| `voxel-forge` | Ran the desktop app | Launcher, degrades gracefully |
| `voxel-forge-mcp --help` | Ignored args, blocked | Prints usage, exits 0 |
| Runtime dependencies | No upper bounds | Capped below next major |
| Installation docs | Windows-only paths | `uv tool install` |

## The three installed commands

Installing the project now puts three commands on the `PATH`:

| Command | What it does |
| --- | --- |
| `voxel-forge-mcp` | The MCP server, on stdio. An MCP client runs this one. |
| `voxel-forge-bridge` | The WebSocket/HTTP bridge on its own |
| `voxel-forge` | The native desktop application |

The entry points are unchanged in name, so an existing MCP client
configuration that already names `voxel-forge-mcp` keeps working. What changes
is that the command is now expected to be installed rather than reached through
a checkout.

## Install from the repository

```bash
uv tool install git+https://github.com/leynos/voxel-forge
```

For the desktop application, add the `desktop` extra:

```bash
uv tool install 'voxel-forge[desktop] @ git+https://github.com/leynos/voxel-forge'
```

From a checkout the equivalent is `uv sync`, or `uv sync --extra desktop` for
the desktop application.

## `voxel-forge` without the `desktop` extra

The `voxel-forge` command is installed whether or not the `desktop` extra is
present, because console scripts and optional dependencies are declared
independently. In 0.1.x the command resolved straight to the PySide6-backed
application, so without the extra it failed with a `ModuleNotFoundError`
traceback.

It now names the missing extra and exits with status 1:

```text
The VoxelForge desktop application requires the optional 'desktop' extra
(missing dependency: PySide6).
Install it with one of:
  uv tool install 'voxel-forge[desktop] @ git+https://github.com/leynos/voxel-forge'
  uv sync --extra desktop  (from a checkout)
```

Anything that treated a non-zero exit from `voxel-forge` as an unexplained
crash should now read the message instead: a missing extra is an expected
state, not a defect.

## `voxel-forge-mcp --help`

`voxel-forge-mcp --help` (and `-h`) now prints usage and exits with status 0
without starting the bridge or binding a socket. In 0.1.x the arguments were
ignored: the server started on stdio and blocked, so a help query hung rather
than returning.

With no arguments the command behaves as before and blocks on stdio, which is
what an MCP client expects.

## Dependency bounds

The runtime dependencies now carry upper bounds: `mcp>=1.9.0,<2`,
`websockets>=14.0,<17`, and `httpx>=0.28.0,<1`. The bounds matter because
`uv tool install` performs a fresh dependency resolution and does not read
`uv.lock`, so without them a new installation was free to select the 2.x line
of `mcp`, where `mcp.server.fastmcp` no longer exists and the server fails at
import.

An environment resolved from the 0.1.x lockfile is unaffected; a fresh install
receives the bounded versions.

## Windows batch wrappers

`run-mcp.bat`, `run-desktop.bat`, `run-editor.bat`, and `build-desktop.bat`
remain available as conveniences for a Windows checkout, and they are still
Windows-only. They are no longer the primary documented route, and `run-mcp.bat`
invokes the installed entry point through `uv run voxel-forge-mcp` rather than
running the files under `src/` directly.

## See also

- [Users guide](users-guide.md) — installation, the commands, MCP client
  setup, and where scenes and exports are stored.
- [Developers guide](developers-guide.md) — the entry-point mapping, the
  launcher boundary, and the verification gates.
