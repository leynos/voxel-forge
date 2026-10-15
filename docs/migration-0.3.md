# Migrating to VoxelForge 0.3

This document records API compatibility changes planned for the 0.3 release.
The project metadata remains at version 0.2.0 while this work is in progress;
this document does not change or announce a package version. Apply these
instructions when upgrading an integration to a 0.3 release.

The [users guide](users-guide.md) describes the supported Python export
helpers. This document describes changes for existing integrations and saved
scene files.

## Export helper arguments become keyword-only

The Python helpers `voxel_forge.vox_io.export_obj` and
`voxel_forge.export_roblox.to_luau_merged` now require their optional
configuration arguments by keyword. Calls that pass those values positionally
raise `TypeError` and must be updated.

These positional calls now fail:

```python
export_obj(scene, path, False)
to_luau_merged(scene, "workspace", False)
```

With an existing scene and destination `path`, write both formats like this:

```python
from voxel_forge.export_roblox import to_luau_merged
from voxel_forge.vox_io import export_obj

obj_path = export_obj(scene, path, merge_boxes=False)
luau_source = to_luau_merged(scene, parent="workspace", anchor=False)
```

Calls that rely on the defaults or already use keyword arguments need no
change. The MCP tool names and their request schemas are unchanged.

## Persisted scene JSON requires declared types

Scene loading now rejects JSON values that older decoding coerced into a
plausible value. Valid scene files retain the same format, but fields must
carry their declared JSON types:

- Block coordinates and `active_layer` must be integers. Booleans, numeric
  strings, and fractional numbers are rejected.
- Layer `name` and block colour values must be strings.
- Layer `visible` must be a JSON boolean (`true` or `false`).
- RGB palette channels must be integers from 0 through 255; booleans and other
  coercible values are rejected.

Malformed data raises `ValueError` through the scene-validation error type.
Inspect and correct affected saved JSON files before loading them with 0.3.
The Python runtime requirement remains Python 3.11 or newer.

## The editor bridge is now opt-in

In 0.2 the MCP server started the editor bridge in the background as part of
startup. An integration could therefore assume that a bridge was available as
soon as the server was running, and a loopback port was bound whether or not
an editor would ever connect.

The server no longer starts the bridge on its own. With no arguments it binds
no socket and serves MCP on stdio, which is what a headless, sandboxed, or
continuous-integration run needs. To keep a listener that the server starts,
ask for one:

```bash
voxel-forge-mcp --bridge
```

Setting `VOXELFORGE_BRIDGE=1` has the same effect, for a client that cannot
add an argument.

Integrations that call the `voxelforge_launch_editor` MCP tool need no change:
that tool still starts the bridge on demand and reports the editor URL.
Editing a scene notifies a bridge that is already running but never starts
one, so a session that only edits and exports stays headless.

Clients that call only the MCP scene and export tools need no change at all.
MCP tool names and their request schemas are unchanged; only the timing of
bridge startup has changed.

## See also

- [Users guide](users-guide.md) — supported export helper calls.
- [Developers guide](developers-guide.md) — project module boundaries and
  verification gates.
- [Migrating to 0.2](migration-0.2.md) — the earlier installed-command
  changes.
