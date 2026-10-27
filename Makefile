# RGCopy developer tasks. `make help` lists them.
PY ?= python3
VENV ?= .venv
BIN := $(VENV)/bin
NPM := npm --prefix frontend

.DEFAULT_GOAL := help
.PHONY: help install build run serve integrate dev-api dev-ui test e2e lint format typecheck check wheel docker clean

help: ## Show this help
	@grep -E '^[a-z0-9-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "} {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

$(BIN)/python:
	$(PY) -m venv $(VENV)
	$(BIN)/pip install --upgrade pip

# Reinstalled whenever pyproject.toml changes (a new dependency after a git pull)
$(VENV)/.installed: pyproject.toml | $(BIN)/python
	$(BIN)/pip install -e ".[dev,desktop]"
	@touch $@

install: $(VENV)/.installed ## Install backend (editable, dev + desktop extras) and frontend deps
	$(NPM) ci

build: ## Build the web UI into rgcopy/web/dist
	$(NPM) run build

# `rgcopy` itself rebuilds the UI when frontend/ changed since the last build
run: $(VENV)/.installed ## Launch the desktop app
	$(BIN)/rgcopy

serve: $(VENV)/.installed ## Run the web server on http://localhost:8000
	$(BIN)/rgcopy serve --open

integrate: $(VENV)/.installed ## Menu entry + Ctrl+V takeover in Nautilus, Nemo, Caja (and Dolphin's menu)
	$(BIN)/rgcopy integrate

dev-api: ## Backend with a fixed dev token (pair with `make dev-ui`)
	RGCOPY_TOKEN=dev RGCOPY_AUTOBUILD=off $(BIN)/rgcopy serve --port 8000 --log-level debug

dev-ui: ## Vite dev server with hot reload on http://localhost:5173/auth?token=dev
	$(NPM) run dev

test: ## Run the Python test-suite (uses real rsync)
	$(BIN)/pytest -q

e2e: ## Ctrl+V takeover in real file managers under Xvfb (as a regular user)
	PATH="$(abspath $(BIN)):$$PATH" tests/e2e/paste_takeover.sh

lint: ## Ruff lint + format check
	$(BIN)/ruff check rgcopy tests
	$(BIN)/ruff format --check rgcopy tests

format: ## Auto-format Python code
	$(BIN)/ruff format rgcopy tests
	$(BIN)/ruff check --fix rgcopy tests

typecheck: ## mypy + TypeScript
	$(BIN)/mypy
	$(NPM) run typecheck

check: lint typecheck test ## Everything CI runs

wheel: build ## Build a wheel with the UI embedded into dist/
	$(BIN)/pip wheel --no-deps -w dist .

docker: ## Build the Docker image
	docker build -t rgcopy:latest .

clean: ## Remove build artifacts and caches
	rm -rf dist build rgcopy/web/dist .pytest_cache .mypy_cache .ruff_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
