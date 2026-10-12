.PHONY: check-fmt lint typecheck test markdownlint nixie

PYTHON_FORMAT_PATHS := \
	src/voxel_forge/bridge.py \
	src/voxel_forge/desktop/launch.py \
	src/voxel_forge/desktop/viewport.py \
	src/voxel_forge/model.py \
	src/voxel_forge/procedural.py \
	src/voxel_forge/scene_store.py \
	src/voxel_forge/server.py \
	src/voxel_forge/vox_io.py \
	tests

# Overridable so continuous integration can supply `npx --yes markdownlint-cli2`
# without duplicating the file list. There is no repository-level markdownlint
# configuration, so the maintained files are enumerated rather than globbed:
# a glob would descend into node_modules.
MDLINT ?= markdownlint-cli2

MARKDOWN_PATHS := \
	README.md \
	docs/developers-guide.md \
	docs/execplans/readiness-gate.md \
	docs/roadmap.md \
	docs/users-guide.md

check-fmt:
	uv run ruff format --check $(PYTHON_FORMAT_PATHS)

lint:
	uv run ruff check src tests

typecheck:
	cd editor && npm exec tsc -- --noEmit

test:
	uv run pytest -q

markdownlint:
	$(MDLINT) $(MARKDOWN_PATHS)

nixie:
	nixie
