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

An integration that scrapes the server's standard error for the bridge
endpoint should additionally watch the lifecycle lines. A bridge start is now
reported once, with the request that caused it, and a stop is reported when
the listeners end:

```text
VoxelForge server: operation=bridge_start trigger=launch_editor
VoxelForge bridge: operation=bridge_state bridge_state=down error_category=CancelledError
```

`error_category` names the class of whatever ended the listeners; an ordinary
shutdown cancels the task, so it reports `CancelledError`. A tool call that
finds the bridge already running reports no start, so a counter over
`bridge_start` measures transitions rather than calls. None of these lines are
written to standard output, which stays reserved for MCP protocol data.

## MCP responses are now English, and the two lookup failures differ

The MCP tool descriptions and their responses were Thai in 0.2. They are
English in 0.3. Tool names and request schemas are unchanged, so an
integration that calls tools by name and passes the same arguments needs no
change **unless it matches on response text**.

If it does, there are three things to update:

1. **Confirmations are English sentences.** The wording is documented in the
   [users guide](users-guide.md#what-the-tools-say-back), which is the
   authority for the text rather than this page.
2. **Not every response is a sentence.** `voxelforge_list_scenes`,
   `voxelforge_get_info`, and `voxelforge_default_palette` return JSON;
   `voxelforge_preview` returns a summary followed by an ASCII rendering; and
   `voxelforge_merge_stats` and the editor tools return several labelled
   lines. Parse the JSON ones rather than matching on text.
3. **The two scene-lookup failures are now distinct.** A session with no
   scene at all reports one message and tells the caller to create a scene; a
   session that has scenes but not the one named reports a different message
   and names both `voxelforge_load` and the alternative of using an existing
   name. In 0.2 both were a bare "not found", so a client that treated every
   lookup failure the same way will now see two cases it has to tell apart.

A client that matches on the old Thai strings, or that assumes one line per
response, is the case this section exists for. The recovery messages are
written as the instruction to follow, so matching on a fragment such as
`voxelforge_load` is more stable than matching the whole sentence.

## See also

- [Users guide](users-guide.md) — supported export helper calls.
- [Developers guide](developers-guide.md) — project module boundaries and
  verification gates.
- [Migrating to 0.2](migration-0.2.md) — the earlier installed-command
  changes.
