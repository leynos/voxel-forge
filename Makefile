.PHONY: fmt check-fmt lint lint-python dead-code install-nose duplication \
        lint-editor typecheck test test-editor markdownlint nixie

# All gates share caches and must stay sequential, including under make -j.
.NOTPARALLEL:

# Overridable so continuous integration can supply `npx --yes markdownlint-cli2`
# without duplicating the file list. There is no repository-level markdownlint
# configuration, so the maintained files are enumerated rather than globbed:
# a glob would descend into node_modules.
MDLINT ?= markdownlint-cli2

PYTHON_TARGETS := src/voxel_forge tests
# Managed PyPy 3.12 is PyPy 8; keep the parser version explicit.
PYLINT_PYTHON ?= pypy@3.12
PYLINT_VERSION ?= 4.0.9
PYLINT = uv tool run --managed-python --python $(PYLINT_PYTHON) \
	--from 'pylint==$(PYLINT_VERSION)' pylint --load-plugins=
DF12_PYTHON ?= 3.14
DF12_PYTHON_LINTS_REF := v0.4.0
DF12_PYTHON_LINTS = git+https://github.com/leynos/df12-python-lints.git@$(DF12_PYTHON_LINTS_REF)
DF12_PYLINT_MESSAGES := R9101,C9102,R9103,R9104,C9105,C9106,C9107,R9108,R9109,R9110,R9111,R9112,C9112
DF12_PYLINT = uv tool run --managed-python --python $(DF12_PYTHON) \
	--from 'pylint==$(PYLINT_VERSION)' --with '$(DF12_PYTHON_LINTS)' \
	pylint --disable=all --load-plugins=df12_python_lints \
	--enable=$(DF12_PYLINT_MESSAGES)
SKYLOS = uv tool run --managed-python --python $(DF12_PYTHON) \
	--from 'df12-python-lints[skylos] @ $(DF12_PYTHON_LINTS)' df12-skylos
DUPLICATION_GATE = uv tool run --managed-python --python $(DF12_PYTHON) \
	--from '$(DF12_PYTHON_LINTS)' df12-duplication

MARKDOWN_PATHS := \
	README.md \
	README.th.md \
	docs/developers-guide.md \
	docs/migration-0.2.md \
	docs/migration-0.3.md \
	docs/users-guide.md \
	AGENTS.md \
	docs/roadmap.md \
	docs/lint-standards.md \
	docs/execplans/readiness-gate.md

fmt:
	uv run ruff format src tests
	uv run ruff check --select I --fix src tests
	cd editor && bun run fmt

check-fmt:
	uv run ruff format --check src tests

lint: lint-python dead-code duplication

lint-python:
	uv run ruff check src tests
	$(PYLINT) $(PYTHON_TARGETS)
	$(DF12_PYLINT) $(PYTHON_TARGETS)

dead-code:
	$(SKYLOS) check --repository .

install-nose:
	$(DUPLICATION_GATE) install --repository .

duplication: install-nose
	$(DUPLICATION_GATE) check --repository .

lint-editor:
	cd editor && bun run check:fmt
	cd editor && bun run lint

typecheck:
	cd editor && bun run check:types

test:
	uv run pytest -q

test-editor:
	cd editor && npm run build
	cd editor && npm test

markdownlint:
	$(MDLINT) $(MARKDOWN_PATHS)

nixie:
	nixie
