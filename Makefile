VENV := .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

.PHONY: install install-frontend test test-frontend test-integration lint check build-frontend run dev package clean

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

test-frontend: ## frontend unit tests (vitest)
	cd frontend && pnpm run test

test-integration: ## full integration tests (spawns real RNS nodes; takes minutes)
	$(PY) -m pytest tests/integration -m integration -q

lint: ## ruff + svelte-check
	$(VENV)/bin/ruff check meshdeck tests
	cd frontend && pnpm run check

check: test test-frontend lint ## everything CI runs

run: ## start the daemon + web UI (dev)
	$(PY) -m meshdeck --verbose

dev: build-frontend run ## build UI then start

package: build-frontend ## one-file binary with embedded UI (PyInstaller)
	$(PIP) install --quiet pyinstaller
	$(VENV)/bin/pyinstaller packaging/pyinstaller.spec --distpath dist --workpath build --noconfirm
	@echo ""
	@echo "Binary: dist/meshdeck   (serve it, run: ./dist/meshdeck)"

clean:
	rm -rf frontend/node_modules frontend/dist .pytest_cache .ruff_cache build dist meshdeck.spec.bak
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
