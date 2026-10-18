VENV := .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

.PHONY: install install-frontend test test-integration lint check build-frontend run dev clean

install: ## create venv + install backend with dev deps
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev]"

install-frontend: ## install frontend dependencies
	cd frontend && pnpm install

build-frontend: ## build the web UI into frontend/dist
	cd frontend && pnpm run build

test: ## unit tests (fast)
	$(PY) -m pytest tests/unit -q

test-integration: ## full integration tests (spawns real RNS nodes; takes minutes)
	$(PY) -m pytest tests/integration -m integration -q

lint: ## ruff + svelte-check
	$(VENV)/bin/ruff check waypoint tests
	cd frontend && pnpm run check

check: test lint ## everything CI runs

run: ## start the daemon + web UI (dev)
	$(PY) -m waypoint --verbose

dev: build-frontend run ## build UI then start

clean:
	rm -rf frontend/node_modules frontend/dist .pytest_cache .ruff_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
