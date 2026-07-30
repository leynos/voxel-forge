.PHONY: fmt check-fmt lint lint-editor typecheck test markdownlint nixie

# Overridable so continuous integration can supply `npx --yes markdownlint-cli2`
# without duplicating the file list. There is no repository-level markdownlint
# configuration, so the maintained files are enumerated rather than globbed:
# a glob would descend into node_modules.
MDLINT ?= markdownlint-cli2

MARKDOWN_PATHS := \
	README.md \
	AGENTS.md \
	docs/roadmap.md \
	docs/execplans/readiness-gate.md

fmt:
	uv run ruff format src tests
	uv run ruff check --select I --fix src tests
	cd editor && bun run fmt

check-fmt:
	uv run ruff format --check src tests

lint:
	uv run ruff check src tests
	uv run pylint src/voxel_forge tests

lint-editor:
	cd editor && bun run check:fmt
	cd editor && bun run lint

typecheck:
	cd editor && bun run check:types

test:
	uv run pytest -q

markdownlint:
	$(MDLINT) $(MARKDOWN_PATHS)

nixie:
	nixie
