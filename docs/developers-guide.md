# VoxelForge developers guide

This guide records the parts of VoxelForge that a contributor has to know
before changing it: how the installed commands map onto modules, why two of
those entry points are shaped the way they are, what tooling the project
assumes, and which checks a change must pass. It complements the
[users guide](users-guide.md), which describes the tool as an operator sees
it.

## Repository layout

- `src/voxel_forge/` — the Python package, including the MCP server
  (`server.py`), the editor bridge (`bridge.py`), the scene model
  (`model.py`), persistence (`scene_store.py`), and the MagicaVoxel reader
  and writer (`vox_io.py`).
- `src/voxel_forge/desktop/` — the PySide6 desktop application.
- `editor/` — the Three.js/Vite web editor.
- `tests/` — the pytest suite.
- `docs/` — this guide, the users guide, the roadmap, and the execution
  plans under `docs/execplans/`.

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

`src/voxel_forge/bridge.py` binds `127.0.0.1:8765` for WebSocket and
`127.0.0.1:8766` for the HTTP scene endpoint, so both are loopback-only. The
bridge announces its ports on standard error, because standard output belongs
to the MCP protocol on the server path.

## Toolchain and dependency requirements

- Python 3.11 or newer; `requires-python` is `">=3.11"`.
- Node.js for the web editor. Continuous integration builds it with Node 22.
- Runtime dependencies are bounded below the next breaking major:
  `mcp>=1.9.0,<2`, `websockets>=14.0,<17`, and `httpx>=0.28.0,<1`.
- The `desktop` extra adds `PySide6>=6.6.0` and `pyinstaller>=6.0`.
- Ruff with `select = ["E", "F", "I", "UP"]` is the lint rule set.

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
| `make check-fmt` | `uv run ruff format --check` over maintained Python paths |
| `make lint` | `uv run ruff check src tests` |
| `make typecheck` | `cd editor && npm exec tsc -- --noEmit` |
| `make test` | `uv run pytest -q` |
| `make markdownlint` | Markdown lint over the maintained Markdown files |
| `make nixie` | Mermaid diagram validation |

`make markdownlint` takes its linter from the `MDLINT` variable, which
defaults to `markdownlint-cli2`. The hosted workflow overrides it with
`npx --yes markdownlint-cli2`, so the gate runs the same way locally and in
continuous integration without duplicating the file list. The Markdown files
it covers are enumerated in the `Makefile` rather than globbed, because a glob
would descend into `node_modules`.

The hosted workflow, `.github/workflows/readiness.yml`, runs on every pull
request and on pushes to `main`. It runs the lint, format, and test gates,
and adds work the local gates do not cover:

- `uv build --wheel`, which proves the distribution still builds;
- `npm ci --prefix editor` to install the editor dependencies from the
  lockfile;
- a build of the editor;
- `npm audit --prefix editor --audit-level=high`, which fails the build on a
  high-severity advisory in the editor's dependency tree.

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
- The Windows batch wrappers stay Windows-only and stay secondary to the
  cross-platform invocation, rather than becoming the documented route.

## Windows batch wrappers

`run-mcp.bat`, `run-desktop.bat`, `run-editor.bat`, and `build-desktop.bat`
are conveniences for a checkout on Windows. They are not a supported path on
other platforms, and documentation that mentions them has to say so: a
reader on Linux who follows them verbatim is misled. `run-mcp.bat` calls the
installed entry point through `uv run voxel-forge-mcp`; it does not run the
files under `src/` directly.

The web editor launch path is portable and is what the
`voxelforge_launch_editor` MCP tool directs the caller to on every platform:
`cd editor && npm install && npm run dev`, then open
`http://localhost:5173`. The tool previously named a Windows-only `.bat`
wrapper, which was a defect for every other platform.
