.PHONY: check-fmt lint typecheck markdownlint nixie

PYTHON_FORMAT_PATHS := \
	src/voxel_forge/bridge.py \
	src/voxel_forge/desktop/viewport.py \
	src/voxel_forge/model.py \
	src/voxel_forge/procedural.py \
	src/voxel_forge/server.py \
	src/voxel_forge/vox_io.py \
	tests

check-fmt:
	uv run ruff format --check $(PYTHON_FORMAT_PATHS)

lint:
	uv run ruff check src tests

typecheck:
	cd editor && npm exec tsc -- --noEmit

markdownlint:
	markdownlint README.md docs/execplans/readiness-gate.md

nixie:
	nixie
