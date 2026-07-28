# VoxelForge roadmap

This roadmap sequences the work needed for VoxelForge to serve as content
tooling for [Thysalion](https://github.com/leynos/thysalion), an isometric
voxel role-playing game. It is written from Thysalion's side of the boundary:
each phase states what Thysalion needs and what VoxelForge would have to become
to supply it. It does not describe VoxelForge's own product direction, and
nothing here obliges the project to take that direction.

The shape follows the GIST model. Each phase carries one testable idea — a bet
that can be wrong. The steps beneath a phase work toward validating or
falsifying that bet, and tasks are review-sized execution units. The roadmap
promises no dates.

The governing requirements live in Thysalion's design documents: the voxel
world model and authoring pipeline (`thysalion-design.md` §7), the material
fields whose fixed-point representation voxel types must match (§10.5), the
knowledge plane that supplies concept identifiers (§11), and the save-archive
content hashes that constrain any canonical encoding (§12.3). The scene format
those sections describe is delivered by Thysalion roadmap step 1.2, and its
execution plan is the concrete specification an exporter would target.

The reference implementation for the packaging and process-hosting work in
phase 1 is [simulacat](https://github.com/leynos/simulacat), a Python package
that bundles a Bun-hosted TypeScript service inside its own wheel and
supervises it as a subprocess. Its `simulacat/orchestration.py`,
`simulacat/js_root.py`, `simulacat/install_simulator_deps.py`, and its
`[tool.hatch.build]` include and force-include rules are the pattern to follow
rather than to invent. VoxelForge has the same shape of problem — a Python
process that must own the lifecycle of a JavaScript one — and currently solves
it with sibling directories, batch files, and fixed ports.

## Licensing and the fork boundary

VoxelForge is MIT-licensed (`LICENSE`, copyright thanakon228). Thysalion is
ISC. The two are compatible, and MIT imposes no obligation to publish
downstream changes.

The README's references to the GNU General Public License are attribution, not
a licence grant, and they are easy to misread because they are in Thai. The
blockquote states that Goxel is GPL-3.0 and that VoxelForge is a new,
MCP-first implementation which does not fork Goxel's C code, sharing only the
interchangeable `.vox` and `.obj` formats; the footer repeats that the
VoxelForge code is the author's own. That position is sound in principle — a
file format is not itself copyrightable, and an independent implementation of
one carries no obligation from the other project's licence — but it is a claim
about provenance rather than a verified fact, and it becomes load-bearing the
moment a fork is published. Task 1.4.3 addresses it.

Thysalion nevertheless adopts a stricter boundary as policy rather than as
licence compliance: no VoxelForge code is incorporated into Thysalion, in
either direction, and any changes made to VoxelForge for Thysalion's benefit
are published. The reason is architectural, not legal. VoxelForge is content
tooling and Thysalion's design is explicit that the authoring pipeline "is
content tooling, not runtime: the engine consumes only the scene format"
(§7.4). A code boundary that is never crossed is the cheapest way to keep that
true. The interface between the two projects is therefore a file format and a
command-line contract, never a library.

One consequence shapes the whole roadmap: VoxelForge must be able to produce
Thysalion's scene format without depending on Thysalion. Phase 3 resolves that
by having VoxelForge consume the published JSON Schema rather than reimplement
the format from prose.

## 1. The tool installs and runs anywhere

Idea: if VoxelForge installs as a single `uv tool` command and runs headless on
Linux as well as Windows, then a project can adopt it as content tooling
without vendoring it, without a bespoke launcher, and without a graphical
session — which is the precondition for everything else in this roadmap.

This phase contains no voxel work. Its deliverable is the ability to depend on
VoxelForge at arm's length.

### 1.1. Make `uv tool install` produce a working command

This step answers whether VoxelForge can be consumed as an installed tool
rather than as a checked-out project. The packaging is already close: the
wheel builds cleanly and declares three console scripts. The failures are in
the dependency envelope and in the platform assumptions of the launchers.

- [ ] 1.1.1. Bound the `mcp` dependency below the next major version.
  - `pyproject.toml` requires `mcp>=1.9.0` with no upper bound, while
    `uv.lock` pins 1.28.1. A fresh resolution — which is exactly what
    `uv tool install` performs, because it ignores the lockfile — selects the
    2.x line, where `mcp.server.fastmcp` no longer exists, and
    `src/voxel_forge/server.py` fails at import.
  - Audit `websockets` and `httpx` for the same unbounded-major exposure.
  - Success: `uv tool install git+https://github.com/leynos/voxel-forge`
    followed by `voxel-forge-mcp --help` succeeds on a machine with no
    checkout and no lockfile.
- [ ] 1.1.2. Make the desktop entry point degrade gracefully without its
  extra.
  - `voxel-forge` resolves to `voxel_forge.desktop.app:main`, but PySide6 is
    an optional `desktop` extra, so an installed tool exposes a command that
    fails with an import traceback.
  - Success: running `voxel-forge` without the extra prints an actionable
    message naming the extra to install, and exits non-zero without a
    traceback.
- [ ] 1.1.3. Replace the Windows-only launchers with a documented
  cross-platform invocation.
  - `run-mcp.bat`, `run-editor.bat`, `run-desktop.bat`, and
    `build-desktop.bat` are the only documented entry points, and the README
    gives absolute `C:\Users\...` paths. The Python itself is portable —
    data directories already use `Path.home()`.
  - Keep the `.bat` wrappers for Windows convenience; document the installed
    console scripts as the primary interface.
  - Success: the README's install and run instructions can be followed on
    Linux without translation, and a Linux machine reaches a running MCP
    server.

### 1.2. Host the editor as a supervised Bun process

This step answers whether the Three.js editor can travel inside the wheel and
be owned by the Python process, rather than living in a sibling directory that
only exists in a checkout. It is the difference between an installed tool that
works and one whose editor command is broken by construction. Follow
simulacat's orchestration module rather than designing this afresh.

Three defects make the current arrangement unshippable, and each is a task
below. `voxelforge_launch_editor` resolves the editor as
`Path(__file__).resolve().parents[2] / "editor"` — walking up from
`src/voxel_forge/server.py` to the repository root. Installed into
`site-packages`, that path lands inside the virtual environment and the editor
is never found. The bridge binds three fixed ports — 8765 for WebSocket, 8766
for HTTP, and 5173 for Vite — so a second instance collides and a busy port
fails outright. And `ALLOWED_EDITOR_ORIGINS` hard-codes `:5173`, which couples
the origin check to the fixed port and would reject any dynamically allocated
one.

- [ ] 1.2.1. Move the editor to Bun and bundle it into the wheel.
  - Replace the `editor/` npm and Vite project with a Bun-served application,
    and include its entry point, `package.json`, and lockfile in the built
    distribution through `[tool.hatch.build]` include and force-include rules.
  - Resolve the bundled root through `importlib.resources` so the same code
    path works from a checkout and from an installed wheel.
  - Success: `uv tool install` followed by the editor command opens a working
    editor on a machine with no checkout.
- [ ] 1.2.2. Spawn and supervise the editor process from Python.
  - Requires 1.2.1.
  - Launch Bun with explicit arguments and `shell=False`, read its stdout on a
    reader thread so the pipe cannot deadlock, and stop it with a bounded
    timeout that escalates from terminate to kill.
  - Success: the editor process is reaped when the server exits, including on
    an abnormal exit, verified by asserting no orphan remains.
- [ ] 1.2.3. Discover ports from the child process instead of fixing them.
  - Requires 1.2.2.
  - Have the Bun process bind an ephemeral port and report it as a structured
    event on stdout; have Python parse that event and wait for it with a
    timeout. Derive the permitted editor origin from the discovered port
    rather than from a constant.
  - Success: two VoxelForge instances run concurrently without collision, and
    an instance starts successfully when 8765, 8766, and 5173 are all occupied.
- [ ] 1.2.4. Provide dependency-installation and root-resolution commands.
  - Requires 1.2.1.
  - Mirror `python -m simulacat.js_root` and
    `python -m simulacat.install_simulator_deps`: one command prints the
    bundled JavaScript package root, another runs `bun install` against it.
    Continuous integration and shell scripts need both without guessing paths.
  - Success: a fresh continuous-integration job can install the editor's
    dependencies knowing only the installed Python package.

### 1.3. Prove headless operation under continuous integration

This step answers whether VoxelForge works without a display, a browser, or a
WebSocket peer. Thysalion's continuous integration has none of those, and any
scene-generation step it runs must not require them. It also decides whether
the bridge is a component or an assumption.

- [ ] 1.3.1. Make the WebSocket bridge opt-in rather than automatic.
  - `voxel_forge.server.main` calls `_ensure_bridge()` before
    `mcp.run(transport="stdio")`, so every invocation starts a background
    listener on a loopback port whether or not an editor will connect. A
    headless or sandboxed run should not bind a port.
  - Success: a documented flag or environment variable runs the server with no
    listening socket, verified by asserting the port is unbound.
- [ ] 1.3.2. Extend the readiness workflow to Linux.
  - `.github/workflows/readiness.yml` and the `Makefile` gates run the
    existing suite; add a Linux matrix entry covering `uv tool install` from a
    clean checkout, the headless server start, and a scene export.
  - Success: the workflow fails if 1.1.1's dependency bound regresses.

### 1.4. Establish the fork and contribution boundary

This step answers how changes made for Thysalion flow back, and records the
code-boundary policy where a future contributor will find it. It exists
because the boundary is easy to erode silently once two projects share a
format.

- [ ] 1.4.1. Record the interface contract and the code boundary in this
  repository.
  - State that the interface between VoxelForge and any consuming game is a
    file format plus a command-line contract, never a library; that VoxelForge
    takes no dependency on a consumer; and that a consumer vendors no
    VoxelForge code.
  - Record the licence position accurately: MIT, with downstream publication a
    policy choice rather than an obligation.
  - Success: a new contributor can tell from the repository alone which
    changes are in scope for the shared format and which are not.
- [ ] 1.4.2. Translate the README and the tool descriptions into English.
  - The README, the `FastMCP` instructions string in
    `src/voxel_forge/server.py`, and several error messages are in Thai. The
    MCP instructions and tool docstrings are read by language models and by
    contributors, and are the tool's primary discovery surface.
  - Keep a Thai translation alongside if the maintainer wants one; the
    requirement is that an English reader can operate the tool.
- [ ] 1.4.3. Substantiate the clean-room claim in the repository.
  - The README asserts that VoxelForge does not fork Goxel's C code. Publishing
    a fork makes that assertion something downstream users rely on, so it
    should be recorded in English, in a file a reader will find, alongside what
    *is* shared: the `.vox` and `.obj` formats, and the `.vox` reader and
    writer in `src/voxel_forge/vox_io.py`, which were written against the
    published format specification.
  - Success: a reader can determine the provenance of the format handling
    without reading Thai and without taking the claim on trust.

## 2. Voxels carry meaning, not just colour

Idea: if a palette entry can carry material semantics — per-face passability,
slope, light emission, simulation coefficients, and an ontology identifier —
alongside its colour, then a VoxelForge scene can describe a game world rather
than only a picture of one. If it cannot, VoxelForge remains a prop and
set-dressing tool and the consuming game authors semantics separately, which
is a materially smaller role.

This is the phase that decides how much of the roadmap is worth doing. A
VoxelForge voxel is currently a 24-bit RGB colour and nothing else, resolved
through `VoxelScene.resolve_color` from either a palette key or a `#RRGGBB`
literal. Thysalion's `VoxelType` (design §7.2) carries a name, a material
class, `[bool; 6]` passability, a slope direction, emission on a 0–15 scale
with a colour, fixed-point simulation coefficients, and an optional concept
Internationalized Resource Identifier (IRI). Colour cannot encode any of that,
so without this phase every later phase is limited to geometry.

### 2.1. Promote the palette from colours to voxel types

This step answers whether a semantic palette can be added without breaking the
existing colour-keyed scenes, the web editor, or the `.vox` interchange. Its
outcome determines whether phases 3 to 5 are reachable.

- [ ] 2.1.1. Extend palette entries from an RGB triple to a named voxel type
  carrying an open attribute map.
  - `VoxelScene.palette` is `dict[str, tuple[int, int, int]]`. Widen it to a
    record holding the display colour plus a free-form attribute mapping, and
    keep the existing colour-only form loadable so tracked scenes still open.
  - Deliberately do not hard-code Thysalion's attribute names. VoxelForge
    should not know what passability is; it should carry attributes it does
    not interpret. That is what keeps the two projects independent.
  - Success: a scene saved by the current version loads unchanged, and a scene
    carrying attributes round-trips through save and load without loss.
- [ ] 2.1.2. Expose voxel-type attributes through the MCP tool surface.
  - Requires 2.1.1.
  - Extend `voxelforge_set_palette` (or add a sibling) so an agent can define a
    voxel type with attributes, and extend `voxelforge_get_info` to report
    them.
  - Success: an agent can define a named material with attributes and read
    them back in one session without touching the filesystem.
- [ ] 2.1.3. Carry attributes across the `.vox` boundary through a sidecar.
  - Requires 2.1.1.
  - The MagicaVoxel format has no field for arbitrary attributes and caps the
    palette at 255 colours, so attributes cannot survive a `.vox` round trip.
    Write them to a sidecar file beside the export and read it back on import
    when present.
  - Success: exporting and re-importing a scene with attributes preserves them
    when the sidecar is present, and degrades to colours alone when it is not,
    with a warning rather than a silent loss.
- [ ] 2.1.4. Preserve attributes through the web editor and the bridge.
  - Requires 2.1.1 and 2.1.2.
  - `src/voxel_forge/bridge.py` synchronizes scenes to the Three.js editor;
    an editor that does not understand attributes must not drop them when it
    writes back.
  - Success: placing a voxel in the editor and saving from the server
    preserves every attribute the palette carried beforehand.

## 3. Export a scene the game can load

Idea: if VoxelForge can emit Thysalion's scene document directly and validly,
then authoring a fixture scene becomes a three-dimensional activity rather than
an exercise in editing text rasters. The bet is that a schema-driven exporter
can be built and maintained without either project importing the other's code;
if that proves impossible, the honest fallback is that VoxelForge exports an
intermediate form and Thysalion owns the final conversion.

### 3.1. Consume the published schema rather than reimplementing the format

This step answers whether the format boundary can be maintained mechanically.
Two independent implementations of one schema drift silently, so the question
is whether the schema can be authoritative enough to prevent that. Its answer
shapes every later export task.

- [ ] 3.1.1. Add a schema-validated export target driven by a committed JSON
  Schema.
  - Thysalion publishes a generated JSON Schema for its scene document.
    VoxelForge should read that schema as data and validate its output against
    it, rather than encoding the format's rules in Python.
  - Pin the schema by version and vendor a copy, so an export is reproducible
    without network access.
  - Success: the exporter refuses to emit a document that fails schema
    validation, and a deliberately corrupted export is rejected with a message
    naming the offending path.
- [ ] 3.1.2. Emit the chunk-keyed voxel payload in canonical form.
  - Requires 3.1.1.
  - The document stores voxels as chunk entries sorted by coordinate, with an
    all-single-type chunk elided to a uniform payload, runs chunk-local and
    Z-major, and no two adjacent runs sharing an index.
  - Success: a property test over generated scenes shows the emitted payload
    decodes to the original voxel set, and that re-emitting a decoded payload
    reproduces the same bytes.
- [ ] 3.1.3. Make export byte-deterministic.
  - Requires 3.1.2.
  - Sorted keys, fixed separators and indentation, a fixed trailing newline,
    and one defined run-splitting rule. Emit every field explicitly rather
    than omitting defaults, so the output matches what a `serde`-based reader
    re-serializes.
  - Success: exporting the same scene twice yields identical bytes, and a
    consuming project's own serializer reproduces those bytes from the decoded
    document.
- [ ] 3.1.4. Map voxel-type attributes onto the target format's palette
  entries.
  - Requires 2.1.1 and 3.1.1.
  - The mapping lives in a configuration file, not in code, so a consumer with
    a different attribute vocabulary supplies its own.
  - Success: a scene whose palette carries the consumer's attribute names
    exports with those attributes in the right fields, and an unmapped
    attribute is reported rather than dropped.

### 3.2. Scale past the interchange limits

This step answers whether VoxelForge can handle scenes of the size the design
declares, given that its current ceilings come from `.vox` rather than from its
own model. It matters because Thysalion's scene classes reach 1024 × 1024 × 128
voxels (design §7.1, Table 1).

- [ ] 3.2.1. Replace the flat block dictionary with chunk-oriented storage.
  - `VoxelLayer.blocks` is a single `dict` keyed by an `(x, y, z)` tuple, which
    is workable for props and unworkable for a district. Store by chunk, with
    an absent chunk meaning empty.
  - Success: constructing a scene with a populated region inside a
    1024 × 1024 × 128 declared extent stays within a stated memory budget, and
    the existing tests pass unchanged.
- [ ] 3.2.2. Make the per-call voxel ceiling a property of the transport, not
  of the model.
  - Requires 3.2.1.
  - `MAX_TOOL_VOXELS = 100_000` guards the MCP tools against an agent
    requesting an unbounded fill. That guard is correct for a tool call and
    wrong for a programmatic or command-line invocation, which should be
    bounded by memory instead.
  - Success: a scripted export can produce a scene larger than the tool
    ceiling, while the MCP tools keep their existing guard and error message.

### 3.3. Make export usable from a script and a pipeline

This step answers whether scene generation can run without an agent in the
loop, which decides whether a consuming project can regenerate its fixtures in
continuous integration.

- [ ] 3.3.1. Add a headless command-line interface over the existing scene
  operations.
  - Requires steps 1.1-1.2.
  - Load, export, validate, and report statistics, with exit codes that
    distinguish an invalid scene from a broken tool from a usage error.
  - Success: a shell script can regenerate a scene and fail the build when the
    output changes unexpectedly, with no MCP client and no browser involved.

## 4. Move between text and three dimensions without losing either

Idea: if VoxelForge can read and write the layered-text authoring form that a
consuming project uses for its tracked fixtures — a character legend plus one
raster per populated layer — then designers can work in whichever
representation suits the task, and the text form stays the reviewable one. If
the round trip is lossy, the two representations will diverge and one of them
will quietly become authoritative.

Thysalion's fixture sources are tracked as text precisely so that a fixture
change is reviewable as a diff; a binary or opaque authoring form would forfeit
that. This phase is what lets a 3D editor participate without taking the
reviewability away.

### 4.1. Round-trip the layered-text form

This step answers whether text and three-dimensional editing can share one
source of truth. Its outcome decides whether VoxelForge is an editor for these
fixtures or only a viewer of them.

- [ ] 4.1.1. Import a legend plus layer rasters into a scene.
  - Requires 2.1.1.
  - Read a legend mapping single characters to voxel-type names, and one
    raster per populated layer, honouring a declared content origin and extent
    so a raster covers only the authored sub-box.
  - Reject an unlisted character and a short row rather than padding or
    silently treating them as empty.
  - Success: importing a fixture's sources yields a scene whose voxel set
    matches the same fixture's exported document.
- [ ] 4.1.2. Export a scene back to the layered-text form.
  - Requires 4.1.1.
  - Success: text to scene to text is byte-identical for every tracked
    fixture, asserted as a test, so a designer's 3D edit produces a clean diff
    rather than a whole-file rewrite.
- [ ] 4.1.3. Emit a provenance mapping alongside an export.
  - Requires 4.1.2.
  - Record which layer file and line each chunk came from, so a consuming
    project's validator can point a diagnostic at the text a human wrote
    rather than at a generated coordinate.
  - Success: a diagnostic naming a chunk coordinate can be resolved to a file
    and line without a manual calculation.

## 5. See what was authored

Idea: if VoxelForge can load a game's scene document and display it, then the
class of fault that passes every structural check and is still wrong — a
building resting on nothing, a spawn inside a wall, a stair with no ramp —
becomes visible before it costs a debugging session in a downstream system.

Structural validation answers whether a document is well formed. It cannot
answer whether a world is habitable, and screenshots at diorama zoom hide a
guard standing inside a wall. An inspector is the cheapest instrument for that
gap.

### 5.1. Import the game's scene document

This step answers whether the export path of phase 3 is genuinely reversible,
which is also the strongest available test that the exporter is correct.

- [ ] 5.1.1. Implement the inverse of the schema-driven export.
  - Requires steps 3.1-3.2.
  - Decode chunk entries, uniform payloads, and canonical runs back into a
    scene, carrying palette attributes onto voxel types.
  - Success: importing an exported document and re-exporting it reproduces the
    original bytes for every tracked fixture.
- [ ] 5.1.2. Add region and slice inspection to the command-line interface.
  - Requires 5.1.1 and 3.3.1.
  - Print a bounded region as legend characters, and report per-layer and
    per-material counts.
  - Success: given a coordinate from a downstream diagnostic, an operator can
    view that neighbourhood without opening a graphical editor.

## 6. A prop and set-dressing library

Idea: if VoxelForge can produce reusable stamps — a market stall, a well, a
hearth, an archway — that a consuming project can place into a larger scene,
then it occupies the role that Thysalion's design already reserves for
MagicaVoxel-style imports, and it does so with the semantic attributes a raw
`.vox` file cannot carry.

Design §7.4 already anticipates this: "MagicaVoxel `.vox` import is supported
for props and set-dressing brought in as palette-mapped voxel stamps". This
phase is that sentence, with attributes attached and without the format's
255-colour and 256-per-axis limits.

### 6.1. Deliver stamps as a first-class concept

This step answers whether a reusable sub-scene is worth modelling explicitly,
or whether copying voxels is sufficient. The answer affects how a library of
props is versioned and shared.

- [ ] 6.1.1. Model a stamp as a named, bounded sub-scene with an anchor.
  - Requires 2.1.1.
  - Save, load, and list stamps independently of the scene that uses them.
  - Success: a stamp authored once can be placed into two different scenes at
    different anchors, and editing the stamp does not retroactively alter
    scenes that already placed it.
- [ ] 6.1.2. Place stamps with rotation about the vertical axis.
  - Requires 6.1.1.
  - Restrict rotation to the four quadrants, matching the fixed isometric
    camera that consuming projects of this kind use, rather than implementing
    arbitrary rotation.
  - Success: a stall placed in each of the four quadrants occupies the
    expected footprint, verified by voxel-set comparison rather than visually.

## 7. Deferred extensions

Idea: if the shared format and the tooling around it are already trustworthy
and boring to operate, then the remaining ideas can be judged on their value
rather than being allowed to destabilize the interface every other phase
depends on.

### 7.1. Re-open these on their own merits

- [ ] 7.1.1. Evaluate direct MagicaVoxel and Goxel interoperability beyond the
  existing `.vox` reader, once 2.1.3's sidecar has shown whether attributes can
  survive an external editor at all.
- [ ] 7.1.2. Evaluate publishing to the Python Package Index, which would
  replace the git-based `uv tool install` of 1.1.1 with a version-resolvable
  one.
  - Requires phase 1.
- [ ] 7.1.3. Evaluate a schema-version negotiation mechanism, so one
  VoxelForge build can export for more than one version of a consumer's scene
  format.
  - Requires steps 3.1.
- [ ] 7.1.4. Evaluate whether the web editor should render voxel-type
  attributes — passability arrows, emission glow, material tinting — rather
  than colour alone.
  - Requires 2.1.4.
