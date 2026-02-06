# CLAUDE.md

## Project Overview

Monorepo for unofficial Garmin Messenger (Hermes) protocol client implementations.
Protocol docs live in `docs/`.

## Repository Layout

| Directory | Purpose |
|-----------|---------|
| `clients/python/` | Python client library (pip-installable, src layout) |
| `clients/go/` | Go client library (single `garminmessenger` package) |
| `clients/rust/` | Rust client crate (planned) |
| `clients/c/` | C client library (planned) |
| `apps/` | Standalone applications (CLI, bots) |
| `tests/` | Cross-implementation test infrastructure and fixtures |
| `docs/` | Protocol and API documentation |
| `tools/` | Dev tooling (mock server, protobuf codegen) |
| `research/` | Internal notes (gitignored) |

## Python Client (`clients/python/`)

### Setup

```bash
cd clients/python
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### Key Files

| File | Purpose |
|------|---------|
| `clients/python/src/garmin_messenger/models.py` | Pydantic models matching Hermes wire format |
| `clients/python/src/garmin_messenger/auth.py` | SMS OTP registration + token refresh |
| `clients/python/src/garmin_messenger/api.py` | Hermes REST API client (httpx) |
| `clients/python/src/garmin_messenger/signalr.py` | SignalR WebSocket client for real-time events |
| `clients/python/pyproject.toml` | Package config and dependencies |

### Testing

```bash
make test-python
# or: cd clients/python && python -m pytest tests/ -v
```

## CLI App (`apps/cli/`)

Standalone click-based CLI that wraps the Python client library.

```bash
garmin-messenger login --phone "+1234567890"
garmin-messenger conversations
garmin-messenger messages <CONVERSATION_ID>
garmin-messenger send --to "+1234567890" --message "Hello"
garmin-messenger listen
```

## Go Client (`clients/go/`)

### Setup

```bash
cd clients/go
go mod tidy
go test ./... -v
```

### Key Files

| File | Purpose |
|------|---------|
| `clients/go/models.go` | All structs, enums, and JSON deserialization (50+ types) |
| `clients/go/auth.go` | SMS OTP registration + token refresh (HermesAuth) |
| `clients/go/api.go` | Hermes REST API client (HermesAPI) |
| `clients/go/signalr.go` | SignalR WebSocket client for real-time events |
| `clients/go/otauuid.go` | OTA UUID generator (Garmin's custom bit layout) |

### Testing

```bash
make test-go
# or: cd clients/go && go test ./... -v
```

### Module

`github.com/slush-dev/garmin-messenger` — single flat package `garminmessenger`.

## Go CLI App (`apps/go-cli/`)

Cobra-based CLI that wraps the Go client library. Same commands as Python CLI.

```bash
garmin-messenger login --phone "+1234567890"
garmin-messenger conversations
garmin-messenger messages <CONVERSATION_ID>
garmin-messenger send --to "+1234567890" --message "Hello"
garmin-messenger listen
```

### Build

```bash
make build-go   # outputs bin/garmin-messenger
```

## Build Orchestration

Bootstrap everything from a clean clone:

```bash
./scripts/build_all.sh
source .venv/bin/activate
```

Or use the top-level Makefile (requires an active venv):

```bash
make help          # list all targets
make test          # run all tests
make test-python   # just Python tests
make lint          # lint all code
make build-python  # pip install -e ".[dev]"
make build-cli     # pip install -e apps/cli
make test-go       # Go client tests
make lint-go       # Go client lint (go vet)
make build-go      # build Go CLI binary
```

## Important Rules

- **Never install packages system-wide.** Always use a virtualenv per client.
- **Do not commit `research/`**, it is just a symlink outside the project.
- **`research/` notes are the source of truth.** Also see `docs/api-reference.md` for the full Hermes API reference.
- **Shared test fixtures** go in `tests/fixtures/` so all implementations use identical test data.
- **Use TDD pattern when writing new features or fixing bugs.** Always plan and write failing tests which show wanted behavior, before implementation. Fix until tests pass.
