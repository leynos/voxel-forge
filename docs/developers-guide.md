# VoxelForge developers guide

This guide records the parts of VoxelForge that a contributor has to know
before changing it: how the installed commands map onto modules, why two of
those entry points are shaped the way they are, what tooling the project
assumes, and which checks a change must pass. It complements the
[users guide](users-guide.md), which describes the tool as an operator sees
it.

## Repository layout

- `src/voxel_forge/` — the Python package, including the MCP composition
  root (`server.py`), editor bridge (`bridge.py`), scene model, persistence,
  and MagicaVoxel reader and writer.
- `src/voxel_forge/desktop/` — the PySide6 desktop application.
- `editor/` — the Three.js application served by Bun.
- `tests/` — the pytest suite.
- `docs/` — this guide, the users guide, the roadmap, and the execution
  plans under `docs/execplans/`.

## Module boundaries

`model.py` is the public domain-model facade. `model_layer.py`,
`model_scene.py`, `model_decode.py`, and `model_validation.py` hold the
focused scene types and operations; `scene_registry.py` owns the in-memory
`SceneStore`, and `scene_store.py` owns JSON persistence. Import model types
from `voxel_forge.model` unless a change is specifically within one of those
implementation modules.

`server.py` is the MCP composition root. It creates the `FastMCP` instance
and shared `SceneStore`, then imports `server_tools` modules to register their
tools. The `build.py`, `edit.py`, `io.py`, and `scene.py` modules deliberately
use the `server` facade's registry, publisher, and operation helpers. Those
globals are the internal integration points that keep MCP edits and bridge
updates on the same store; preserve their names and the registration order
when moving tools. The `server` facade also re-exports the established tool
callables and file-format functions.

The desktop `app.py` composes the main window from menu, file, export, create,
and help mixins, with the sidebar and viewport as separate components. In the
web editor, `scene-data.ts` owns the scene wire types, bridge-payload
selection, palette colour lookup, and per-layer colour grouping. `main.ts`
owns browser state, rendering, picking, and input.

## Scene lookup failures

A scene lookup has two failure modes and they need different remedies, so
they are two types rather than one. Both live in `scene_errors.py` and both
derive from `KeyError`, so a caller that only needs "there is no scene" can
keep catching that. They sit apart from `model_validation.py` because that
module holds *field* validation — palette values, name length, voxel size
bounds — and a registry that raises a lookup failure should not import those
to spell it. `model_validation.py` re-exports the two names so older imports
keep working; new code imports from `scene_errors` directly.

- `NoCurrentSceneError` — the caller named nothing and nothing was current.
  The remedy is to create a scene.
- `UnknownSceneError` — the caller named a scene that is not registered. The
  remedy is to load a saved scene or correct the name.

The messages on those types are **transport-neutral**: neither names an MCP
tool. That is deliberate. Putting the recovery wording in the domain would
make the domain model depend on the tool surface, which is the adapter's
concern, and it would put wording the guides quote in two places instead of
one.

`server.resolve_scene(store, scene_name, *, operation=...)` is that adapter.
It is the single place a lookup failure becomes caller-facing text, branching
on the exception **type** rather than on message content, and it is what every
scene tool calls for a target lookup. The store is passed in rather than read
from the module global so the translation can be tested against a store of its
own; tool modules pass `server.store`, so the process still has exactly one.

`operation` is keyword-only and required, and its value comes from the closed
set in `SceneOperation` (`scene_errors.py`). A tool that resolves a scene
without naming its operation would leave a log record nobody can act on, so
the parameter has no default. `server._edit_scene` forwards the same label for
the two tools that edit through the context manager.

A tool that resolves a scene directly through `SceneStore.get` or
`SceneStore.select` bypasses the recovery wording and will disagree with its
neighbours — `voxelforge_select_scene` did exactly that until a test
parametrized across ten tools caught it. The rule for a new tool is therefore
narrow and testable: resolve targets through `server.resolve_scene`, and add a
`SceneOperation` member for what the tool does.

The same boundary is where the failure is logged, for the reason above:
`resolve_scene` still knows which domain type it caught, while the message it
builds names an MCP tool and a scene name the log should not hold. The record
names both the category and the operation:

```text
scene lookup failed operation=place_many category=unknown_scene
```

The category says what went wrong; the operation says which tool the caller
reached for. Without the second field every failing edit logs the same line as
every failing export.

The tests pin all of it. `tests/test_failure_messages.py` checks the recovery
wording and the per-category log lines, and its
`test_every_scene_name_tool_gives_the_same_lookup_remedy` asserts on the
*message* across the tool set rather than on which helper a tool happens to
call. `tests/test_scene_lookup_logging.py` drives every advertised
scene-resolving tool and requires each to log its own `operation=` label; it
also asserts set equality between the tools driven and the scene-resolving
part of the advertised surface, in both directions, so a new tool cannot
silently escape the check. The same module pins the query side of the
boundary: `preview`, `get_info`, and `merge_stats` reach the adapter too, and
a lookup that *succeeds* must log nothing and publish no scene update, so a
query stays distinguishable from a command in the log.
`tests/test_model_readiness.py` pins the domain side: the exception types and
their transport-neutral messages.

## The consumer boundary

VoxelForge is content tooling that other projects consume; it is not a runtime
they link against. The full statement of that boundary is in
[fork-and-interface-boundary.md](fork-and-interface-boundary.md), and the part
that constrains a change here is this:

- The interface to a consumer is a **file format plus a command-line and MCP
  contract**. A consumer invokes the installed tool and reads the files it
  produces.
- VoxelForge takes **no dependency on a consumer**. Where a consumer publishes
  a machine-readable specification, the tool consumes that specification as
  pinned, vendored data rather than importing the consumer's code — the same
  shape as reading any other published format.
- A consumer **vendors no VoxelForge code**, and VoxelForge does not become a
  shared library in either direction. A change that would move the interface
  toward a linked library is out of scope, however convenient it looks.

This rule governs the boundary **between projects**. Importing the installed
package is allowed, and that is not in tension with the Python export helpers
the [users guide](users-guide.md) documents: those are a supported in-process
API, and an integration may install `voxel-forge` and call them. The
distinction is between a versioned dependency on a released package and code
co-owned across projects. Importing an installed package keeps the version
boundary — the helper is called by name and version, and breaking it is a
release note. Vendoring source, or sharing types that both projects edit in
lockstep, dissolves that boundary, and it is the second that is out of scope in
either direction.

The reason to keep this written down rather than assumed is that the boundary
erodes quietly. Two projects that share a file format have an obvious reason to
want shared types, and a shared type is the first edge of a shared library.
Routing the same information through a file or a documented command costs
almost nothing while the projects are young and is very expensive to undo
later.

Changes *in* scope include anything that makes VoxelForge better as a
stand-alone tool, anything that lets it read or write a format a consumer
publishes from that format's own specification, and fixes or tests that keep
the published formats round-tripping faithfully.

## Console scripts

Every user-facing command is a console script declared in `pyproject.toml`
under `[project.scripts]`, which maps a command name onto a callable:

| Command | Entry point |
| --- | --- |
| `voxel-forge-mcp` | `voxel_forge.server:main` |
| `voxel-forge-bridge` | `voxel_forge.bridge:main` |
| `voxel-forge` | `voxel_forge.desktop.launch:main` |

The three are independent: the bridge can run on its own, and the MCP server
starts a bridge only when it is explicitly asked to, with `--bridge` or
`VOXELFORGE_BRIDGE=1`, or on demand when an MCP client calls the
`voxelforge_launch_editor` tool.

## The desktop extra and the launcher boundary

`voxel-forge` is installed whether or not the optional `desktop` extra is
present, because console scripts and optional dependencies are declared
independently. The command therefore has to cope with PySide6 being absent,
which is why the entry point is `voxel_forge.desktop.launch:main` rather than
the application module itself.

`src/voxel_forge/desktop/launch.py` is deliberately a thin launcher between
the console entry point and the application in
`src/voxel_forge/desktop/app.py`. It imports the application inside a
`try` block and classifies an `ImportError`:

- If the failure names the optional GUI stack, the launcher prints an
  actionable message to standard error naming the missing distribution and
  the command that installs the extra, and returns `1`. No traceback is
  printed.
- If the failure is anything else, the launcher re-raises it, so a genuine
  defect still surfaces as a traceback rather than being misreported as a
  missing extra.
- On the normal path with the extra present, the launcher does not return at
  all: it hands control to the application, which terminates the process
  itself through `sys.exit(app.exec())` once the window closes.

The classifier, `_names_missing_desktop_extra(exc: ImportError) -> bool`, is a
pure predicate and is the unit under test. It matches the missing name
against the top-level distributions that only the `desktop` extra installs,
and it tolerates dotted names so a nested import such as `PySide6.QtCore` is
still recognized.

A subtlety is worth recording, because it looks like a bug and is not one.
When PySide6 is absent, CPython reports the missing *distribution* in
`ImportError.name`, so the classifier sees `PySide6`. When PySide6 is
installed but its native libraries cannot load — a headless Linux host missing
`libEGL.so.1`, for example — CPython reports the *leaf* extension name
instead, such as `QtCore`, with the exception's `path` naming the `.so`.
The launcher deliberately treats that second case as unrelated to the extra,
so the traceback naming the missing native library survives rather than being
replaced by advice to install an extra that is already present. Do not widen
the classifier to catch it.

Because the classifier compares only the module name, it cannot be tested
through the real import machinery on a machine that has the extra installed;
the test suite forces the failure instead.

## MCP entry-point behaviour

`src/voxel_forge/server.py:main` builds an `argparse` parser with the program
name `voxel-forge-mcp`, parses the arguments, and only then starts the bridge
and runs the server on stdio. Argument parsing precedes the bridge on purpose:
`--help` and `-h` must print usage and exit with status 0 without binding a
socket, and anything that bound a port first would make a help query a
side-effecting operation. `argparse` raises `SystemExit` for `--help`, so the
server is reached only once parsing returns normally.

Starting the bridge is opt-in. `--bridge` starts the listener eagerly, before
stdio, and `VOXELFORGE_BRIDGE=1` seeds that flag's default so a wrapper that
cannot express the request in an argument list can still make it. Without
either, no socket is bound at startup. `main` is one of the two places that
start a bridge; the other is `server_tools/io.py`, reached when an MCP client
calls `voxelforge_launch_editor`. That is the on-demand path.

Scene mutations take a third route. `_sync_bridge` is notify-only: it returns
immediately unless `bridge.current_ports()` reports a bound bridge, so an edit
can never start a listener the run did not ask for. A headless session stays
headless however many edits it makes, and only an editor request or an eager
flag binds a port.

With no arguments, the server starts on stdio and blocks. That blocking
behaviour is the contract an MCP client depends on.

`_announce_startup` writes one line to standard error with stable fields, so a
headless run and a run whose bridge failed to start are distinguishable even
though both block on stdio:

```text
VoxelForge server: operation=server_start bridge_mode=headless bridge_state=down
```

`bridge_mode` records what was requested, `headless` or `eager`, and
`bridge_state` records what was reached, `down` or `running`. The state is
read back through `current_ports()`, so `running` is printed only when ports
are actually bound. An eager start that fails raises out of `_ensure_bridge`
before the line is printed, so the announcement never claims a state the
process did not hold. Standard output stays reserved for the MCP protocol, so
a client reading stdout never has to filter diagnostics.

Starting and stopping the listener have their own diagnostics, so the bridge
lifecycle is legible from the log without reading the code:

```text
VoxelForge server: operation=bridge_start trigger=server_start
VoxelForge bridge: operation=bridge_state bridge_state=down error_category=CancelledError
```

`bridge_start` is emitted once per transition from down to up, and names the
`trigger` that caused it: `server_start` for the eager `--bridge` or
`VOXELFORGE_BRIDGE=1` path, `launch_editor` for the on-demand path an MCP
client reaches through `voxelforge_launch_editor`. A later launch request
against an already-running bridge is a no-op and emits nothing, so the line
counts starts rather than calls. `bridge_state=down` is emitted once from the
`finally` that clears the published ports, with `error_category` naming the
exception class that ended the listeners. The ordinary shutdown is a
cancellation and therefore reports `CancelledError`; `none` means the task
left the loop without raising, which is not the normal path. Only the class is
recorded, never its message, which may carry bound ports or editor-supplied
data.

The standalone `voxel-forge-bridge` command defaults to WebSocket port 8765 and
HTTP port 8766. The MCP server instead binds ephemeral loopback ports and
passes the discovered values to the editor. The bridge announces its ports on
standard error, because standard output belongs to the MCP protocol on the
server path.

The WebSocket bridge checks a supplied `Origin` against the registered editor
origins. It accepts connections with no `Origin` header for non-browser
clients. Both services bind to loopback, which limits network reachability but
does not authenticate local users or processes; treat these checks as browser
cross-origin protection, not as an authentication boundary.

## Toolchain and dependency requirements

- Python 3.11 or newer; `requires-python` is `">=3.11"`.
- Base Pylint runs under managed PyPy 8; df12 Pylint, Skylos, and Nose run
  under managed CPython 3.14. Both Pylint passes check Python 3.11 syntax.
- Bun for the web editor server, dependencies, and tests. Continuous
  integration installs Bun with `oven-sh/setup-bun`.
- The editor uses TypeScript with strict compiler options, Biome for
  formatting and lint, and oxlint with `df12-lints`.
- Editor tests use `fast-check` (`^4.10.2`) for grouping and bridge-endpoint
  properties, plus Playwright (`^1.64.1`) with Chromium for the built-page
  bridge workflow.
- Python boundary tests use Hypothesis to generate editor-origin ports,
  HTTP content lengths, and process-supervision state sequences.
- Runtime dependencies are bounded below the next breaking major:
  `mcp>=1.9.0,<2`, `websockets>=14.0,<17`, and `httpx>=0.28.0,<1`.
- The `desktop` extra adds `PySide6>=6.6.0` and `pyinstaller>=6.0`.
- Ruff, base Pylint, and the df12 Pylint plugin check the supported Python
  baseline. Skylos and Nose add blocking dead-code and duplication checks.
  Their interpreter split, versions, roots, and policy are recorded in the
  [lint standards](lint-standards.md).

Those bounds are load-bearing rather than decorative. `uv tool install`
performs a fresh dependency resolution and does not read `uv.lock`, so the
bounds in `pyproject.toml` — not the versions in the lockfile — decide what a
new installation receives. Without an upper bound on `mcp`, a fresh
resolution selects the 2.x line, where `mcp.server.fastmcp` no longer exists
and `src/voxel_forge/server.py` fails at import. A contract test pins each
intended cap rather than merely requiring that some upper bound exists.

## Verification gates

The `Makefile` drives the gates. Run them sequentially rather than in
parallel: the build cache is shared, and running one gate at a time is what
lets each benefit from what the previous one cached.

| Target | What it runs |
| --- | --- |
| `make fmt` | Format Python and editor files and fix Python import order |
| `make check-fmt` | Check Python formatting with Ruff |
| `make lint` | Run Python lint, dead-code, and duplication gates |
| `make lint-python` | Run Ruff and both Pylint passes |
| `make dead-code` | Run the blocking Skylos scan |
| `make install-nose` | Install the pinned Nose detector under `.tools/` |
| `make duplication` | Install and run the blocking Nose scan |
| `make lint-editor` | Check editor formatting and run Biome and oxlint |
| `make typecheck` | Check editor sources and positive/negative type fixtures |
| `make test` | Run Python tests with pytest |
| `make test-editor` | Run the Bun editor tests |
| `make markdownlint` | Lint the maintained Markdown files |
| `make nixie` | Validate Mermaid diagrams |

`make test-editor` runs the Bun editor tests. The Bun handler tests exercise
the production placement and removal functions with controlled WebSocket
states; the fast-check property test verifies per-colour grouping and input
order. The Playwright browser test starts the real Bun server through
`serve.ts` against a temporary Python bridge with real HTTP and WebSocket
endpoints. It removes a voxel from layer 0 while layer 1 is active, then
places a voxel through mouse input. These browser assertions complement the
focused handler tests rather than replacing them.

The hosted workflow installs editor packages with
`bun install --frozen-lockfile --cwd editor`, then installs Chromium using
Playwright before `make test-editor`. Serving and testing the editor does not
run a production editor build. The separate `uv build --wheel` step packages
the Python distribution and its editor assets into the wheel.
For a local run, install the browser once with
`cd editor && bunx playwright install chromium`.

The installed package includes the editor, but contributor scripts and CI may
need its package directory without a source checkout. Resolve that directory
with:

```sh
python -m voxel_forge.js_root
```

This prints the absolute editor package root containing `package.json`. To
install the editor dependencies from the installed package, run:

```sh
python -m voxel_forge.install_editor_deps
```

This resolves the same package root and runs `bun install` there.

See the [lint standards](lint-standards.md) for the detailed contributor
sequence and scanner configuration. Make disables parallel target execution
so shared caches are used sequentially.

`make markdownlint` takes its linter from the `MDLINT` variable, which
defaults to `markdownlint-cli2`. The hosted workflow overrides it with
`npx --yes markdownlint-cli2`, so the gate runs the same way locally and in
continuous integration without duplicating the file list. The Markdown files
it covers are enumerated in the `Makefile` rather than globbed, because a glob
would descend into `node_modules`.

The hosted workflow, `.github/workflows/readiness.yml`, runs on every pull
request and on pushes to `main`. It runs the checks sequentially: Python
formatting and lint, editor dependency installation, Python tests, Python
wheel build, editor format and lint, TypeScript check, Chromium installation,
editor delivery tests, dependency audit, and Markdown lint. The delivery
tests serve the editor through Bun; the wheel build packages the Python
distribution and editor assets. The workflow does not currently run the
local `make nixie` target.

The workflow also runs an `install` job, which covers the installed artifact
rather than the checkout. It runs `uv tool install .` from a clean checkout,
so the resolution is fresh and a regression in a dependency bound fails the
job rather than being masked by the lockfile. It then runs
`voxel-forge-mcp --help`, and then `python3 tests/installed_smoke.py`. That
driver launches the installed command from the `PATH` and drives a real MCP
stdio session: the `initialize` handshake, a scene build, and a `.vox` export,
asserting throughout that the process never held a listening socket. It is
stdlib-only and never imports `voxel_forge`, so it can only exercise the
installed distribution and not the checkout.

That socket assertion is only worth as much as the probe behind it, so
`tests/listener_probe.py` queries the child's own `/proc` entry and
`tests/test_listener_probe.py` is the probe's control group: it starts a child
that genuinely binds a loopback port and requires the probe to see it, and it
proves the probe does not attribute one process's listener to another. The
probe answers with a `ListenerReport` rather than a bare list, because an empty
list is ambiguous between "no listening socket" and "the tables could not be
read". Only `ProbeOutcome.MEASURED` with no ports certifies a headless run;
`UNSUPPORTED` (no `/proc` on this host) and `FAILED` (the tables exist but
could not be read) both fail the driver, so a platform where the check cannot
run reports a failure rather than a vacuous pass.

## Decisions

These are the compatibility decisions the project has settled, recorded so
they are not relitigated by accident.

- The `voxel-forge` entry point is a launcher rather than the desktop
  application directly, so that an installed tool that lacks the `desktop`
  extra degrades with a message instead of a traceback.
- Runtime dependencies carry upper bounds, because a fresh `uv tool install`
  ignores the lockfile and would otherwise be free to select a breaking major.
- The launcher classifies only the failure of the optional GUI stack and
  re-raises everything else, so that a missing native library and a genuine
  import defect are not confused with a missing extra.
- The bridge announces its ports on standard error and keeps standard output
  for protocol data, so a client reading stdout never has to filter
  diagnostics.
- Starting the editor bridge is opt-in. `--bridge` and `VOXELFORGE_BRIDGE=1`
  start it eagerly, before stdio, and `voxelforge_launch_editor` starts it on
  demand; a scene mutation only notifies a bridge that is already running. The
  bridge is therefore a component a caller asks for rather than an assumption
  every run makes, which is what lets a headless or sandboxed session bind no
  port at all.
- The Three.js editor ships in the wheel and runs as a supervised Bun process.
  The MCP server discovers its bridge and editor ports at startup. Bun closes
  its server when the supervisor's private stdin pipe reaches EOF, so forced
  Python termination cannot leave the editor listening as an orphan.
- The Windows batch wrappers stay Windows-only and stay secondary to the
  cross-platform invocation, rather than becoming the documented route.

## Editor hosting architecture

`editor_runtime.editor_entrypoint()` resolves `voxel_forge/editor/serve.ts`
from the installed package first, then falls back to `editor/serve.ts` in a
repository checkout. `editor_package_root()` returns the corresponding
directory for dependency installation. The installed package must be
filesystem-backed: Bun needs a durable script path and a writable
`node_modules` directory, so archive-only resources fail with an actionable
error.

`server_tools/io.py` composes the MCP launch operation: it ensures the bridge,
passes the discovered bridge ports to Bun, supervises the child through
`orchestration.py`, registers its discovered editor origin, and reports the
browser URL. The editor reports its bound port as a structured stdout event
and serves the bridge endpoints through `/bridge.json`. The private stdin pipe
lets Bun close its listener when the Python supervisor exits, even if Python's
`atexit` handlers do not run.

## Windows batch wrappers

`run-mcp.bat`, `run-desktop.bat`, `run-editor.bat`, and `build-desktop.bat`
are conveniences for a checkout on Windows. They are not a supported path on
other platforms, and documentation that mentions them has to say so: a
reader on Linux who follows them verbatim is misled. `run-mcp.bat` calls the
installed entry point through `uv run voxel-forge-mcp`; it does not run the
files under `src/` directly.

The `voxelforge_launch_editor` MCP tool starts the bundled editor under the
MCP server, opens it in the browser, and reports its URL. Bun must be installed
on the host. For manual development from a checkout, run
`cd editor && bun install && bun run dev`, then open
`http://127.0.0.1:5173`.

The packaged editor must be filesystem-backed or extracted to a directory (a
checkout also works): Bun needs a real directory for `serve.ts` and
`node_modules`, so archive-only resources are unsupported.
