# Assistant instructions

## Code style and structure

- **Code is for humans.** Write code with clarity and empathy—assume a
  tired teammate will need to debug it at 3 a.m.
- **Comment *why*, not *what*.** Explain assumptions, edge cases, trade-offs,
  or complexity. Don't echo the obvious.
- **Clarity over cleverness.** Be concise, but favour explicit over terse or
  obscure idioms. Prefer code that's easy to follow.
- **Use functions and composition.** Avoid repetition by extracting reusable
  logic. Prefer generators or comprehensions, and declarative code to
  imperative repetition when readable.
- **Small, meaningful functions.** Functions should have a clear purpose,
  single responsibility, and obey command/query segregation.
- **Clear commit messages.** Commit messages should be descriptive, explaining
  what was changed and why.
- **Use consistent spelling and grammar.** Comments and documentation must use
  en-GB-oxendict ("-ize" / "-yse" / "-our") spelling and grammar, with the
  exception of references to external APIs. (EXCEPTION: the naming of the
  "LICENSE" file, which is left unchanged for community consistency.)
- **Illustrate with clear examples.** Function documentation must include
  clear examples demonstrating usage and outcome. Test documentation should
  omit examples that only restate the test logic.
- **Keep file size manageable.** No single code file should be longer than 400
  lines. Long switch statements or dispatch tables should be broken up by
  feature and constituents colocated with targets. Large blocks of test data
  should be moved to external data files.
- **Name things precisely.** Use clear, descriptive variable and function
  names. For booleans, prefer names with `is`, `has`, or `should`.
- **Structure logically.** Each file should encapsulate a coherent module.
  Group related code (for example, models + utilities + fixtures) close
  together.
- **Group by feature, not layer.** Colocate views, logic, fixtures, and
  helpers related to a domain concept rather than splitting by type.
- **Use clear file boundaries.** Each module, component, and package should
  have an obvious responsibility and avoid accidental coupling.
- **Keep private helper docstrings concise.** Prefer single-line docstrings
  for private helpers. When a private helper needs an explanatory paragraph,
  inspect whether that need exposes conflated responsibilities, an unclear
  command/query boundary, or another CQRS or cohesion failure:
  - Split the helper when it performs distinct query and command
    responsibilities or combines unrelated concerns.
  - Extract a focused helper when doing so makes the invariant or boundary
    local and simpler.
  - Keep the helper intact when its responsibility is cohesive and the
    explanation documents an unavoidable local constraint; retain the
    paragraph in that case.
- **Structure private helper docstrings selectively.** Use structured
  NumPy-style sections for private helpers only when they describe
  non-obvious behaviour.

## Documentation maintenance

- **Reference:** Use the Markdown files within the `docs/` directory as a
  knowledge base and source of truth for project requirements, dependency
  choices, and architectural decisions. `docs/roadmap.md` sequences the
  planned work.
- **Update:** When new decisions are made, requirements change, libraries are
  added/removed, or architectural patterns evolve, **proactively update** the
  relevant file(s) in the `docs/` directory to reflect the latest state.
- **Bilingual README:** The README is maintained in English (`README.md`) and
  Thai (`README.th.md`). Any change to one must be mirrored in the other in
  the same change set.

## Change quality and committing

- **Atomicity:** Aim for small, focused, atomic changes. Each change (and
  subsequent commit) should represent a single logical unit of work.
- **Quality gates:** Before considering a change complete or proposing a
  commit, ensure all of the following are met:
  - New functionality or behaviour changes are fully validated by relevant
    unit and behavioural tests.
  - Bug fixes include a failing test before the fix and a passing test
    afterward.
  - Code passes lint checks.
  - Formatting is correct and validated.
- **For Python files:**
  - **Testing:** Passes all relevant tests (`make test`).
  - **Linting:** Passes lint checks (`make lint` — Ruff plus Pylint with the
    `df12_python_lints` plugin).
  - **Formatting:** Adheres to formatting standards (`make check-fmt`; use
    `make fmt` to apply fixes).
- **For TypeScript files (the `editor/`):**
  - **Linting:** Passes `make lint-editor` (Biome plus oxlint with the
    `df12-lints` plugin).
  - **Formatting:** Passes `npm run check:fmt` in `editor/` (use
    `npm run fmt` to apply fixes).
  - **Typechecking:** Passes `make typecheck` (`tsc --noEmit` with the strict
    compiler options in `editor/tsconfig.json`).
- **For Markdown files (`.md` only):**
  - **Linting:** Passes markdown lint checks (`make markdownlint`).
  - **Mermaid diagrams:** Passes validation using nixie (`make nixie`).
- **Committing:**
  - Only changes that meet all quality gates should be committed.
  - Write clear, descriptive commit messages that summarize the change,
    following:
    - **Imperative mood** in the subject line (for example, "Fix bug", "Add
      feature").
    - **Subject line length:** around 50 characters or fewer.
    - **Body:** Separate subject from body with a blank line. Explain *what*
      and *why* in wrapped lines (approximately 72 columns).
    - **Formatting:** Use Markdown for formatted text inside the message
      body.
  - Do not commit changes that fail any quality gate.

## Lint suppressions

Every suppression must record a reason the next reader can audit. A bare
`# noqa`, `# pylint: disable=...`, `# type: ignore`, or
`// biome-ignore` without an explanation fails the lint gate.

## Refactoring heuristics and workflow

- **Recognizing refactoring needs:** regularly assess the codebase for
  potential refactoring opportunities. Consider refactoring when you observe:
  - **Long methods/functions:** functions that are excessively long or try to
    do too many things.
  - **Duplicated code:** identical or very similar code blocks appearing in
    multiple places.
  - **Complex conditionals:** deeply nested or overly complex `if`/`else` or
    `switch` statements.
  - **Large code blocks for single values:** significant logic blocks
    dedicated to calculating or deriving one value.
  - **Primitive obsession / data clumps:** groups of simple variables that
    are frequently passed together, which may indicate a missing abstraction.
  - **Excessive parameters:** functions or methods requiring too many
    parameters.
  - **Feature envy:** methods that focus more on other data than their own.
  - **Shotgun surgery:** one change that forces many files to be edited.
- **Abstraction / port / helper policy:** before adding a new abstraction,
  port, or helper:
  - Sweep the repository to confirm there is no existing equivalent helper,
    port, or abstraction.
  - Document the new abstraction's intended scope and re-use policy.
- **Post-commit review:** after functional changes or bug fixes that meet
  quality gates, review changed code and adjacent areas using these
  heuristics.
- **Separate atomic refactors:** if refactoring is required, implement it in
  a separate atomic commit after the functional change and ensure it passes
  all relevant gates.

## Python verification and testing

- For Python work, use `pytest` for unit tests. Cover happy paths, unhappy
  paths, and relevant edge cases.
- Add end-to-end tests where a change affects externally observable
  workflows, integration contracts, persistence, command-line behaviour,
  network boundaries, or other system-level behaviour.
- Use property tests with `hypothesis` when a change introduces an invariant
  over a range of inputs, states, orderings, or transitions.
- Run relevant suites before and after each change.

## Markdown guidance

- Validate Markdown files using `make markdownlint`.
- Validate Mermaid diagrams in Markdown by running `make nixie`.
- Markdown paragraphs and bullet points should be wrapped at 80 columns.
- Code blocks should be wrapped at 120 columns.
- Tables and headings should not be wrapped.
- Use dashes (`-`) for list bullets.
- Use GitHub-flavoured Markdown footnotes (`[^1]`) for references and
  footnotes.

## TypeScript guidance (the `editor/`)

The web editor is implemented in TypeScript and follows the same clarity,
strictness, and reproducibility goals as the Python code.

### Compiler configuration

Keep `editor/tsconfig.json` sharp and strictness enabled:

- `strict: true`
- `noUncheckedIndexedAccess: true`
- `exactOptionalPropertyTypes: true`
- `noImplicitOverride: true`
- `useUnknownInCatchVariables: true`
- `noPropertyAccessFromIndexSignature: true`
- `verbatimModuleSyntax: true` with `import type` / `export type`

### TypeScript style and structure

- **Immutability first**: Prefer `const`, `readonly`, and returning new
  objects over mutating inputs.
- **Functions**: Extract meaningfully named helpers when a function grows
  long or takes on multiple responsibilities.
- **Parameters**: Group related parameters into typed objects rather than
  long positional lists.
- **Predicates**: When branching becomes complex, extract predicate helpers
  or lookup tables. Exhaustive `switch` logic should include a `never` guard.
- **Docs**: Every module begins with a `/** @file … */` block describing
  purpose, responsibilities, and usage.

### Runtime validation and types

- **Runtime schemas**: Validate I/O boundaries such as bridge messages and
  fetched payloads before trusting their shape.
- **Time and randomness**: Centralize `now()` and `rng()` style adapters
  rather than calling `Date.now()` or `Math.random()` directly in logic.

### Error handling

- **Semantic errors**: Use discriminated unions for recoverable conditions
  that callers branch on.
- **Exceptions**: Reserve `Error` subclasses for exceptional paths and attach
  a `cause` where available.

### Linting and formatting

- **Biome**: Use Biome for formatting and linting (`npm run fmt`,
  `npm run lint:biome` in `editor/`).
- **oxlint**: The df12 oxlint plugin enforces module/function JSDoc,
  conditional complexity, and nesting limits (`npm run lint:oxlint`).
- **Type-checking**: Use `npm run check:types` to surface TypeScript issues
  early.
- **Import hygiene**: Keep imports sorted and remove unused or extraneous
  dependencies.

### Dependency management

- **Version policy**: Use caret requirements (`^x.y.z`) for direct
  dependencies unless a narrower range is justified explicitly.
- **Lockfile**: Commit the lockfile. Rebuild it deliberately when major tool
  upgrades require it.
- **Culling**: Prefer small, actively maintained packages and remove
  unmaintained dependencies quickly.

## Key takeaway

These practices help maintain a high-quality codebase and facilitate
collaboration.
