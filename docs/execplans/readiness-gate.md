# Make VoxelForge dependable for basic agent-driven scene creation

This ExecPlan (execution plan) is a living document. The sections
`Constraints`, `Tolerances`, `Risks`, `Progress`, `Surprises & Discoveries`,
`Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work
proceeds.

Status: IN PROGRESS

## Purpose / big picture

After this work, an MCP-capable agent can launch VoxelForge using the documented
command, create and edit a bounded voxel scene, observe the same scene in the
web editor, save and reload it safely, and export a structurally valid
MagicaVoxel `.vox` file. The repository will build reproducibly and will have a
small automated suite and CI workflow that exercise that complete path.

Success is observable by running the sequential gates listed below and seeing
all of them pass, then running the MCP smoke test and observing that stdout
contains only MCP protocol output while bridge diagnostics go to stderr.

## Constraints

- Keep changes limited to the readiness findings recorded in this plan:
  launcher and stdio safety, bridge synchronization and origin checks, editor
  deletion persistence, scene validation and resource bounds, VOX correctness,
  package/build reproducibility, existing lint/type/dependency findings,
  readiness tests, CI, and the documentation needed to describe those changes.
- Preserve the existing MCP tool names and successful-call return shapes. New
  validation errors may reject inputs that were previously unsafe.
- Preserve Python 3.11 compatibility and the existing Windows-first launch
  experience while keeping console entry points portable.
- Do not redesign the desktop UI, procedural generators, mesh merger, OBJ
  exporter, or Roblox exporter beyond removing the duplicate function and
  existing lint failure.
- Do not add authentication infrastructure or a network service. The bridge
  remains loopback-only and accepts browser origins only from the local editor.
- Do not run formatting, lint, type checks, or tests in parallel. Gate each
  commit sequentially and commit each coherent change.
- Use Memtrace before editing existing source symbols and after edits to check
  change scope and impact. Use Leta for precise source navigation where needed.
- Agents working concurrently own disjoint files and must not revert or rewrite
  another agent's changes.

## Tolerances (exception triggers)

- Scope: stop and escalate if the implementation needs more than 18 tracked
  files or 900 net new lines, excluding lockfiles and generated build output.
- Interfaces: stop if an existing MCP tool must be removed or renamed.
- Dependencies: adding `pytest`, Ruff, Three.js declarations, or direct fixed
  versions of already-transitive build packages is permitted; any other new
  runtime dependency requires escalation.
- Compatibility: stop if valid existing scene JSON cannot be migrated by
  validation-compatible loading, or if VOX correctness requires abandoning
  version 150 single-model output.
- Iterations: stop after three unsuccessful implementation attempts for the
  same failing behavioural test and record the evidence in `Decision Log`.
- Security: stop if restricting browser origins prevents the documented local
  Vite editor from connecting without a new user-managed secret.
- Delegation: sub-agents must escalate instead of touching files outside their
  assigned ownership or broadening acceptance criteria.

## Risks

- Risk: cross-thread WebSocket scheduling can race bridge startup.
  Severity: high.
  Likelihood: medium.
  Mitigation: publish the bridge event loop only after server startup, schedule
  with `asyncio.run_coroutine_threadsafe`, and specify pre-start/no-client
  behaviour in focused tests.
- Risk: VOX palette indexing and chunk order can pass a self-reader while still
  violating the external format.
  Severity: high.
  Likelihood: medium.
  Mitigation: assert raw `SIZE`, `XYZI`, and `RGBA` chunk bytes and palette
  indices independently of `import_vox`, plus a round-trip test.
- Risk: strict deserialization can reject previously tolerated malformed data.
  Severity: medium.
  Likelihood: medium.
  Mitigation: accept the documented schema and defaults, reject only unsafe or
  structurally invalid values with actionable errors.
- Risk: dependency refresh can introduce unrelated frontend churn.
  Severity: medium.
  Likelihood: low.
  Mitigation: restrict changes to `editor/package.json` and its lockfile, then
  verify `npm audit`, TypeScript, and Vite build output.

## Progress

- [x] (2026-07-28 12:42Z) Created branch `readiness-gate` from clean `main`.
- [x] (2026-07-28 12:42Z) Indexed the exact repository as Memtrace repo
  `voxel-forge` and inspected context and impact for bridge synchronization,
  `VoxelScene`, and `export_vox`.
- [x] (2026-07-28 12:42Z) Fixed this plan's scope and completion measure.
- [x] (2026-07-28 12:47Z) Added red Python contract tests; 18 tests fail for
  the assessed launcher, bridge, validation, resource-bound, and VOX defects,
  while the Unicode round-trip and basic in-memory agent workflow pass.
- [x] (2026-07-28 13:03Z) Corrected launcher, bridge scheduling/stdout,
  origin handling, and editor deletion persistence; focused synchronization
  tests pass.
- [x] (2026-07-28 13:03Z) Added scene-name/schema/colour/layer validation and
  fill/batch resource limits; focused model and server tests pass.
- [x] (2026-07-28 13:03Z) Corrected VOX `SIZE`/`XYZI`/`RGBA` encoding, palette
  indexing, and coordinate range rejection; raw-format and round-trip tests
  pass against the primary MagicaVoxel version 150 specification.
- [x] (2026-07-28 13:03Z) Corrected wheel configuration, Ruff findings,
  TypeScript declarations, vulnerable frontend resolution, Markdown findings,
  and dependency locking; the corresponding local gates pass.
- [x] (2026-07-28 13:03Z) Added a sequential CI workflow containing the same
  deterministic Python and frontend gates.
- [ ] Run all acceptance gates through the sanctioned gate runner, inspect any
  cited logs, and complete the requirement-by-requirement audit.

## Surprises & discoveries

- Observation: Memtrace was available but the repository was not indexed.
  Evidence: `list_indexed_repositories` returned an empty repository list for
  the workspace, after which exact-path indexing created 183 symbols and 733
  relationships.
  Impact: all pre-edit graph evidence now uses the `voxel-forge` repository.
- Observation: changing `_broadcast` has a high graph impact across 33 symbols,
  while changing `VoxelScene` has critical impact across 94 symbols.
  Evidence: Memtrace `get_impact` results on branch `readiness-gate`.
  Impact: bridge and model edits require narrow contract tests before changes.
- Observation: no project-specific decision was recovered with enough content
  or confidence to govern these fixes.
  Evidence: decision recall returned only low-scoring opaque cross-project
  identifiers.
  Impact: the checked-in code, README contract, and this approved plan remain
  authoritative.
- Observation: the Memtrace graph endpoint exited after initial context and
  impact collection and rejected incremental recovery.
  Evidence: subsequent `get_impact` and `index_directory` calls failed because
  the local MemDB endpoint at port 50051 was unreachable.
  Impact: initial high/critical graph impact results governed the core edits;
  later duplicate-function cleanup used bounded source evidence and Leta.
- Observation: pytest initially imported a stale installed package rather than
  the live `src/` tree.
  Evidence: failure tracebacks pointed into `.venv/site-packages` after source
  edits, and all focused tests passed once pytest's `pythonpath` was explicit.
  Impact: `pyproject.toml` now pins test discovery to `src/`.

## Decision log

- Decision: use branch name `readiness-gate`.
  Rationale: it produces the exact required branch-derived plan path
  `docs/execplans/readiness-gate.md`.
  Date/Author: 2026-07-28 12:42Z / Codex.
- Decision: treat the user's instruction to proceed with implementation as
  approval of this initial plan, so no second approval pause is required.
  Rationale: the request explicitly combines writing and implementing the plan.
  Date/Author: 2026-07-28 12:42Z / Codex.
- Decision: define readiness as the basic headless agent workflow plus honest
  live-editor synchronization and valid single-model VOX output.
  Rationale: this is the smallest boundary that resolves every concrete blocker
  and readiness gap from the assessment without redesigning the product.
  Date/Author: 2026-07-28 12:42Z / Codex.
- Decision: preserve loopback networking and restrict accepted local editor
  origins rather than add credentials.
  Rationale: this directly addresses cross-origin local writes within the
  existing single-user architecture and dependency tolerance.
  Date/Author: 2026-07-28 12:42Z / Codex.
- Decision: allocate VOX palette indices from resolved scene RGB values instead
  of trusting scene palette keys to be numeric.
  Rationale: named and hexadecimal colours are public scene inputs, while the
  VOX format requires indices 1 through 255 and maps RGBA entries 0 through 254
  to those indices.
  Date/Author: 2026-07-28 13:03Z / Codex.
- Decision: consolidate readiness tests and remove incidental formatter churn.
  Rationale: preserve all 22 behavioural contracts and repository-wide lint
  coverage while keeping the final diff within the fixed 18-file tolerance.
  Date/Author: 2026-07-28 13:03Z / Codex.

## Outcomes & retrospective

Implementation is in progress. No production source has been changed yet.

## Context and orientation

`src/voxel_forge/server.py` declares the MCP tools and starts the bridge before
running FastMCP over standard input/output. `src/voxel_forge/bridge.py` owns the
loopback WebSocket and minimal HTTP servers and shares the in-memory
`SceneStore`. `src/voxel_forge/model.py` defines scenes, layers, persistence,
palette resolution, and voxel mutation. `src/voxel_forge/vox_io.py` reads and
writes MagicaVoxel version 150 and Wavefront OBJ files. `editor/src/main.ts`
renders scenes and sends browser edits. `run-mcp.bat`, `pyproject.toml`, and the
frontend manifests define installation and launch behaviour.

The MCP transport is a JSON-RPC byte stream on stdout; ordinary diagnostics on
stdout can make the client unable to parse replies. The bridge uses an asyncio
event loop in a background thread, so synchronous MCP calls must submit
coroutines to that specific loop rather than look for a loop in the MCP thread.
A VOX version 150 single model contains a `SIZE` chunk followed by an `XYZI`
chunk, with an optional `RGBA` palette chunk whose first entry represents
palette index 1.

The baseline has no tests or CI. Python compilation, core imports, the Vite
bundle, and Mermaid validation pass. The documented launcher, wheel build,
Ruff, TypeScript, Markdown lint, and npm audit fail.

## Plan of work

Stage A creates the plan and captures graph-backed impact. This stage ends when
the plan is committed and its Markdown structure passes `markdownlint` and
`nixie`.

Stage B establishes red tests with pytest. Tests will specify safe scene names
and schema validation, bounded fill and batch operations, correct scheduling to
the bridge loop, persisted editor removal, stdout isolation, VOX raw chunk
structure, palette indexing, coordinate limits, and an agent workflow from
creation through save/load/export. Each group must fail for the assessed defect
before production code changes.

Stage C makes the smallest runtime changes that satisfy those contracts. The
bridge will retain its running loop and use thread-safe coroutine submission;
diagnostics will use stderr; WebSocket messages will support both place and
remove operations and reject non-local editor origins. Model and server
boundaries will validate names, scene shape, layers, colours, batch length, and
fill volume before mutation. VOX export will emit the required chunks and reject
dimensions that cannot be represented instead of wrapping them.

Stage D repairs delivery gates. The Windows launcher will call the installed
console entry point. Hatch configuration will build one copy of the package.
Python development dependencies and `uv.lock` will make gates reproducible.
Frontend declarations and the vulnerable PostCSS resolution will be refreshed.
The duplicate generator and unused import will be removed. README formatting
and usage text will describe the corrected launcher and limits. A GitHub Actions
workflow will run the same sequential checks.

Stage E runs the full gate stack and a completion audit. Any failure is fixed
only when it traces to the findings above. Unrelated improvements are recorded
but not implemented.

## Concrete steps

Run all commands from `/home/leynos/Projects/voxel-forge` and capture gate output
with `tee` under `/tmp`.

1. Add `docs/execplans/readiness-gate.md`, validate it, and commit it.
2. Add pytest configuration and focused tests. Run:

   ```bash
   uv run pytest -q | tee /tmp/test-voxel-forge-readiness-gate.out
   ```

   Expect failures that name the launcher, bridge, validation, deletion, and
   VOX behaviours. Commit the red tests after confirming the failures are the
   intended ones.
3. Implement one coherent behaviour group at a time. After each group, rerun
   its focused tests, then `uv run pytest -q`, and commit only when both pass.
4. Refresh frontend dependencies with `npm install --prefix editor`, then run
   TypeScript, build, and audit sequentially.
5. Run the complete validation sequence through the sanctioned gate runner.

## Validation and acceptance

Completion requires all of the following evidence; a narrower pass cannot
substitute for any item.

- `uv sync --locked --all-extras` succeeds from the committed `uv.lock`.
- `uv run pytest -q` passes all tests, including a complete create, place/fill,
  preview, save/load, and VOX-export workflow.
- `uv run ruff check src tests` and the configured Python formatter check pass.
- `uv build --wheel` succeeds and the wheel exposes `voxel-forge-mcp`.
- `timeout 3s uv run python -m voxel_forge.server </dev/null` exits cleanly with
  no non-protocol stdout; bridge diagnostics, if emitted, appear on stderr.
- `npm ci --prefix editor`, TypeScript `--noEmit`, `npm run build --prefix
  editor`, and `npm audit --prefix editor --audit-level=high` pass.
- `markdownlint README.md docs/execplans/readiness-gate.md` and `nixie` pass.
- Raw VOX tests observe `SIZE`, then `XYZI`, then `RGBA`; a colour-index fixture
  round-trips without colour drift; an over-256-cell model raises a clear error.
- A bridge contract test proves an MCP-thread scene update reaches a connected
  client and an editor removal updates the server-side scene.
- The documented launcher uses package/module execution rather than direct
  script execution.
- GitHub Actions contains the same Python and frontend gates in sequential
  steps, and the final worktree is clean.

Quality criteria are zero failing tests, lint errors, type errors, build errors,
high-severity npm advisories, Markdown errors, or unexplained generated diffs.
No benchmark is required; resource safety is proven by rejecting more than
100,000 voxels in one fill or batch operation before allocation or mutation.

## Idempotence and recovery

Dependency installs, tests, builds, and lint commands are safe to rerun. Tests
must redirect scene storage to pytest temporary directories and must not modify
real user data. Build output remains ignored. If dependency refresh fails,
restore only the manifest and lockfile changes from that uncommitted stage; do
not reset the branch. If a bridge smoke test is interrupted, terminate only the
specific process started by that test and confirm no VoxelForge process remains.

## Artefacts and notes

Baseline evidence is stored in `/tmp` with filenames beginning
`py-compile-voxel-forge-main`, `ruff-check-voxel-forge-main`,
`package-build-voxel-forge-main`, `ts-typecheck-voxel-forge-main`,
`editor-build-voxel-forge-main`, `launcher-script-voxel-forge-main`, and
`npm-audit-voxel-forge-main`. These logs are diagnostic evidence only and are
not committed.

## Interfaces and dependencies

Keep every existing `voxelforge_*` MCP tool. Add internal constants in
`server.py` for maximum batch and fill volume, and internal validation helpers
in `model.py` for scene names and serialized scene shape. Bridge notification
must remain `notify_scene_update(scene: VoxelScene) -> None`; its implementation
may use a stored `asyncio.AbstractEventLoop` and
`asyncio.run_coroutine_threadsafe`.

Use pytest for Python behavioural tests and Ruff for Python lint/format checks.
Use the existing TypeScript compiler and Vite for the editor, adding only the
matching Three.js declarations. Do not add a second web framework, VOX library,
state manager, or concurrency abstraction.

## Revision note

2026-07-28 12:42Z: Created the initial approved implementation plan from the
readiness assessment, added fixed tolerances and acceptance evidence, and
recorded Memtrace indexing and impact results. Implementation remains entirely
within the assessed findings.

2026-07-28 12:47Z: Added the red-test evidence and recorded the two behaviours
that already pass. The remaining work is unchanged; production implementation
must turn the 18 expected failures green without weakening their contracts.

2026-07-28 13:03Z: Recorded the green runtime, packaging, frontend,
documentation, and CI milestones. Twenty-two contract tests now pass; only the
independent full-gate report and final completion audit remain.
