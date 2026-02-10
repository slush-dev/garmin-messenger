.PHONY: help test test-python test-python-lib test-python-cli test-go test-go-lib test-go-cli \
       lint lint-python lint-python-lib lint-python-cli lint-go lint-go-lib lint-go-cli \
       build build-python-lib build-python-cli build-go-cli proto-gen clean \
       test-openclaw-plugin build-openclaw-plugin

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------

test: test-python test-go test-openclaw-plugin ## Run all tests

test-python: test-python-lib test-python-cli ## Run all Python tests
test-python-lib: ## Run Python library tests
	cd lib/python && python -m pytest tests/ -v
test-python-cli: ## Run Python CLI tests
	cd apps/python-cli && python -m pytest tests/ -v

test-go: test-go-lib test-go-cli ## Run all Go tests
test-go-lib: ## Run Go library tests
	cd lib/go && go test ./... -v
test-go-cli: ## Run Go CLI tests
	cd apps/go-cli && go test ./... -v

test-openclaw-plugin: ## Run OpenClaw plugin tests
	cd apps/openclaw-plugin && npx vitest run

# ---------------------------------------------------------------------------
# Lint
# ---------------------------------------------------------------------------

lint: lint-python lint-go ## Lint all code

lint-python: lint-python-lib lint-python-cli ## Lint all Python code
lint-python-lib: ## Lint Python library
	cd lib/python && python -m ruff check src/ tests/
lint-python-cli: ## Lint Python CLI
	cd apps/python-cli && python -m ruff check src/ tests/

lint-go: lint-go-lib lint-go-cli ## Lint all Go code
lint-go-lib: ## Lint Go library
	cd lib/go && go vet ./...
lint-go-cli: ## Lint Go CLI
	cd apps/go-cli && go vet ./...

# ---------------------------------------------------------------------------
# Build / Install
# ---------------------------------------------------------------------------

build: build-python-lib build-python-cli build-go-cli build-openclaw-plugin ## Build all

build-python-lib: ## Install Python library in dev mode
	cd lib/python && pip install -e ".[dev]"
build-python-cli: ## Install Python CLI in dev mode
	cd apps/python-cli && pip install -e .
build-go-cli: ## Build Go CLI binary
	cd apps/go-cli && go build -trimpath -ldflags="-s -w -X main.version=$$(git describe --tags --always --dirty)" -o ../../build/go/garmin-messenger .

build-openclaw-plugin: ## Pack OpenClaw plugin tarball into build/
	cd apps/openclaw-plugin && npm run build && npm version --no-git-tag-version --allow-same-version $$(git describe --tags --abbrev=0 | sed 's/^v//') && npm pack --pack-destination ../../build/openclaw-plugin

# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

clean: ## Remove build artifacts
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	rm -rf build/ 2>/dev/null || true
