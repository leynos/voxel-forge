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

## Console scripts

Every user-facing command is a console script declared in `pyproject.toml`
under `[project.scripts]`, which maps a command name onto a callable:

| Command | Entry point |
| --- | --- |
| `voxel-forge-mcp` | `voxel_forge.server:main` |
| `voxel-forge-bridge` | `voxel_forge.bridge:main` |
| `voxel-forge` | `voxel_forge.desktop.launch:main` |

The three are independent: the bridge can run on its own, and the MCP server
starts its own bridge in the background.

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

With no arguments, the server starts on stdio and blocks. That blocking
behaviour is the contract an MCP client depends on.

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
- Editor tests use `fast-check` (`^4.10.2`) for grouping properties and
  Playwright (`^1.64.1`) with Chromium for the built-page bridge workflow.
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

`make test-editor` first builds the production page, then runs three editor
test layers. The Bun handler tests exercise the production placement and
removal functions with controlled WebSocket states; the fast-check property
test verifies per-colour grouping and input order. The Playwright test loads
the built page against a temporary bridge with real HTTP and WebSocket
endpoints, then removes a voxel from layer 0 while layer 1 is active and
places a voxel through mouse input. These browser assertions complement the
focused handler tests rather than replacing them.

The hosted workflow installs editor packages with
`bun install --frozen-lockfile --cwd editor`, then installs Chromium using
Playwright before `make test-editor`. The editor build is also run as its own
CI step after the test target.
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
formatting, Python lint, Python tests, wheel build, editor dependency install,
editor format and lint, TypeScript check, Chromium installation, editor build
and tests, a separate editor build, dependency audit, and Markdown lint. It
does not currently run the local `make nixie` target.

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
- The Three.js editor ships in the wheel and runs as a supervised Bun process.
  The MCP server discovers its bridge and editor ports at startup. Bun closes
  its server when the supervisor's private stdin pipe reaches EOF, so forced
  Python termination cannot leave the editor listening as an orphan.
- The Windows batch wrappers stay Windows-only and stay secondary to the
  cross-platform invocation, rather than becoming the documented route.

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
