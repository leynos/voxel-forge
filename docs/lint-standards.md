# Lint standards

`make lint` runs the Python checks and blocking dead-code and duplication
checks sequentially. CI calls the same target. The runtime remains Python
3.11 or newer; lint tools run in separate managed environments.

## Pylint interpreters

Base Pylint 4.0.9 runs on managed `pypy@3.12` (PyPy 8). The df12 plugin runs
on CPython 3.14, with the same Pylint release and the pinned
`df12-python-lints` v0.4.0 release. The plugin is installed only in its tool
environment, so installing or testing VoxelForge on Python 3.11 never needs
to resolve a dependency requiring Python 3.12.

Both passes read `py-version = "3.11"` from the Pylint configuration.
Running a linter on CPython 3.14 does not change the application's supported
syntax or annotation semantics. Parse errors remain enabled in the base
pass, and df12 messages remain enabled in the plugin pass.

The voxel scene, layer, and mesh-merge records use slotted dataclasses, as
required by the df12 plugin. Their declared fields and persistence formats
remain the application contract.

## Shared scanners

The Skylos and Nose pattern comes from
[Pokie](https://github.com/leynos/pokie). Gate implementation, installation,
report validation, and detector pins belong to `df12-python-lints`; this
repository owns the scan roots and policy in `pyproject.toml`.

- `make dead-code` runs `df12-skylos` with the package's Skylos 4.33.2 pin
  against production Python under `src`. The gate is strict and keeps the
  analysis local, without upload or source rewriting.
- `make install-nose` uses the shared verified installer for Nose 0.20.0.
  The local binary lives under the ignored `.tools/nose` directory.
- `make duplication` installs Nose if necessary, then runs the shared
  blocking gate across `src`, `tests`, and `editor/src`. Syntax, semantic,
  and near-duplicate families are checked with a minimum size of 24 and an
  unlimited report budget (`top = 0`), so ranking cannot hide findings.

Fix underlying issues before committing. Investigate scanner findings against
actual runtime registration and callbacks before removing code. Do not add
exceptions or raise thresholds merely to obtain a passing gate.

## Contributor gates

Run gates one at a time:

```sh
make check-fmt
make lint
make lint-editor
make typecheck
make test
make markdownlint
make nixie
```

Install editor dependencies with `npm ci --prefix editor` before running its
checks. `make` also disables parallel target execution so `make -j` cannot
silently overlap the shared caches.

## Shared application helpers

Duplication fixes keep shared operations at their owning boundary:

- `voxel_forge.paths` owns creation of the application's scene and export
  directories. Existing desktop, persistence, and MCP import surfaces remain
  available; explicit user-chosen paths stay with the file operation.
- `model_validation.validate_layer_index` owns the range check shared by
  scene edits and persisted active-layer validation, preserving each field's
  error label.
- The MCP server's private `_export_path` resolves explicit destinations
  and default scene filenames for its export tools only.
- The background bridge thread uses the same `main` launcher as the foreground
  command, so there is one event-loop startup path.
- Desktop `prompt_scene_name` owns accepted, stripped name input for empty
  scenes and procedural creation. Procedural `_BuildOptions` keeps each
  model's builder and dialog defaults together; build/error handling is local
  to `CreateActionsMixin` and does not generalize other editing actions.
- The editor's `scene-data` module owns scene wire types, bridge payload
  selection, and palette colour resolution, shared by the HTTP/WebSocket
  loading and rendering paths. The main editor module owns browser state,
  rendering, and input, and stays within the 400-line file ceiling.
- Layer counts map the concrete layer-count operation over the scene's layer
  records. Directory APIs bind the common creation function to their own
  paths, rather than repeating forwarding functions.
- Desktop Blender exports share the format-specific writer while retaining
  separate merged/raw feedback. Static help text stays in a local topic table
  and uses one informational-dialog operation.
- The server's `_edit_scene` context owns successful edit publication for
  palette and single-voxel mutation tools. Failure exits without publishing.
  WebSocket edits share one variant dispatcher and one post-edit broadcast.
- Bear-body colour queries check the existing region priority explicitly:
  head first, then body/belly, then limbs. Placement remains a separate
  command over the classified cells; head/body overlaps retain fur colour.
