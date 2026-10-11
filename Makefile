# Every uv call goes through the vendored helper, which cleans the environment,
# uses the global uv cache, runs offline first and goes online at most once. See
# https://github.com/leynos/shared-actions/tree/main/uv_gate for the contract.
UV_GATE ?= python3 scripts/uv_gate.py
UV ?= uv
# The helper finds uv on PATH, so a caller's UV=/path/to/uv is honoured by putting
# that uv's directory first on PATH for every recipe.
export PATH := $(if $(findstring /,$(UV)),$(patsubst %/,%,$(dir $(UV))):)$(PATH)
# A UV given on the command line or in the environment must be an executable file named
# uv: the helper finds uv on PATH by that name and would otherwise use another one.
ifneq ($(filter command line environment,$(origin UV)),)
ifneq ($(findstring /,$(UV)),)
ifeq ($(shell test -f '$(UV)' -a -x '$(UV)' && printf y),)
$(error UV=$(UV) is not an executable file)
endif
ifneq ($(notdir $(UV)),uv)
$(error UV=$(UV) must be named uv)
endif
endif
endif
.PHONY: prepare check-fmt lint typecheck test markdownlint nixie

.DEFAULT_GOAL := check-fmt

prepare: ## Install the locked development environment, offline first
	$(UV_GATE) prepare

PYTHON_FORMAT_PATHS := \
	src/voxel_forge/bridge.py \
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
	docs/roadmap.md \
	docs/execplans/readiness-gate.md

check-fmt: prepare
	$(UV_GATE) run -- ruff format --check $(PYTHON_FORMAT_PATHS)

lint: prepare
	$(UV_GATE) run -- ruff check src tests

typecheck:
	cd editor && npm exec tsc -- --noEmit

test: prepare
	$(UV_GATE) run -- pytest -q

markdownlint:
	$(MDLINT) $(MARKDOWN_PATHS)

nixie:
	nixie
