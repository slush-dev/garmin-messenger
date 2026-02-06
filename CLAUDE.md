# CLAUDE.md

## Project Overview

Monorepo for unofficial Garmin Messenger (Hermes) protocol client implementations.
Protocol docs live in `docs/`.

## Repository Layout

| Directory | Purpose |
|-----------|---------|
| `clients/python/` | Python client library (pip-installable, src layout) |
| `clients/go/` | Go client library (planned) |
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
```

## Important Rules

- **Never install packages system-wide.** Always use a virtualenv per client.
- **Do not commit `research/`**, it is just a symlink outside the project.
- **`research/` notes are the source of truth.** Also see `docs/api-reference.md` for the full Hermes API reference.
- **Shared test fixtures** go in `tests/fixtures/` so all implementations use identical test data.
- **Use TDD pattern when writing new features or fixing bugs.** Always plan and write failing tests which show wanted behavior, before implementation. Fix until tests pass.
