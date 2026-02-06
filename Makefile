.PHONY: help test test-python test-cli test-go lint lint-python lint-cli lint-go build build-python build-cli proto-gen clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------

test: test-python test-cli ## Run all tests

test-python: ## Run Python client tests
	cd clients/python && python -m pytest tests/ -v

test-cli: ## Run CLI app tests
	cd apps/cli && python -m pytest tests/ -v

test-go: ## Run Go client tests
	cd clients/go && go test ./...

# ---------------------------------------------------------------------------
# Lint
# ---------------------------------------------------------------------------

lint: lint-python lint-cli ## Lint all code

lint-python: ## Lint Python client
	cd clients/python && python -m ruff check src/ tests/

lint-cli: ## Lint CLI app
	cd apps/cli && python -m ruff check src/ tests/

lint-go: ## Lint Go client
	cd clients/go && go vet ./...

# ---------------------------------------------------------------------------
# Build / Install
# ---------------------------------------------------------------------------

build: build-python build-cli ## Build all

build-python: ## Install Python client in dev mode
	cd clients/python && pip install -e ".[dev]"

build-cli: ## Install CLI app in dev mode
	cd apps/cli && pip install -e .

# ---------------------------------------------------------------------------
# Protobuf
# ---------------------------------------------------------------------------

proto-gen: ## Regenerate protobuf bindings for all languages
	@echo "Proto generation not yet configured — add per-language targets in tools/proto-gen/"

# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

clean: ## Remove build artifacts
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
