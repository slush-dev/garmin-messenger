# CLAUDE.md

## Project Overview

Monorepo for unofficial Garmin Messenger (Hermes) protocol client implementations.
Protocol docs live in `docs/`.

## Repository Layout

| Directory | Purpose |
|-----------|---------|
| `lib/python/` | Python library (pip-installable, src layout) |
| `lib/go/` | Go library (single `garminmessenger` package) |
| `lib/rust/` | Rust crate (planned) |
| `lib/c/` | C library (planned) |
| `apps/` | Standalone applications (CLI, bots) |
| `tests/` | Cross-implementation test infrastructure and fixtures |
| `docs/` | Protocol and API documentation |
| `tools/` | Dev tooling (mock server, protobuf codegen) |
| `research/` | Internal notes (gitignored) |

## Python Library (`lib/python/`)

### Setup

```bash
cd lib/python
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### Key Files

| File | Purpose |
|------|---------|
| `lib/python/src/garmin_messenger/models.py` | Pydantic models matching Hermes wire format |
| `lib/python/src/garmin_messenger/auth.py` | SMS OTP registration + token refresh |
| `lib/python/src/garmin_messenger/api.py` | Hermes REST API client (httpx) |
| `lib/python/src/garmin_messenger/signalr.py` | SignalR WebSocket client for real-time events |
| `lib/python/pyproject.toml` | Package config and dependencies |

### Testing

```bash
make test-python-lib
# or: cd lib/python && python -m pytest tests/ -v
```

## Python CLI App (`apps/python-cli/`)

Standalone click-based CLI that wraps the Python library.

```bash
garmin-messenger login --phone "+1234567890"
garmin-messenger conversations
garmin-messenger messages <CONVERSATION_ID>
garmin-messenger send --to "+1234567890" --message "Hello"
garmin-messenger listen
```

## Go Library (`lib/go/`)

### Setup

```bash
cd lib/go
go mod tidy
go test ./... -v
```

### Key Files

| File | Purpose |
|------|---------|
| `lib/go/models.go` | All structs, enums, and JSON deserialization (50+ types) |
| `lib/go/auth.go` | SMS OTP registration + token refresh (HermesAuth) |
| `lib/go/api.go` | Hermes REST API client (HermesAPI) |
| `lib/go/signalr.go` | SignalR WebSocket client for real-time events |
| `lib/go/otauuid.go` | OTA UUID generator (Garmin's custom bit layout) |
| `lib/go/fcm/` | Android-native FCM push notifications (subpackage) |

### Testing

```bash
make test-go-lib
# or: cd lib/go && go test ./... -v
```

### Module

`github.com/slush-dev/garmin-messenger` — single flat package `garminmessenger`.

## Go CLI App (`apps/go-cli/`)

Cobra-based CLI that wraps the Go library. Same commands as Python CLI.

```bash
garmin-messenger login --phone "+1234567890"
garmin-messenger conversations
garmin-messenger messages <CONVERSATION_ID>
garmin-messenger send --to "+1234567890" --message "Hello"
garmin-messenger listen

# Registration management (clean up stale FCM tokens)
garmin-messenger registrations list
garmin-messenger registrations delete <instance-id>
garmin-messenger registrations cleanup  # delete ALL registrations
```

### Build

```bash
make build-go-cli   # outputs build/go/garmin-messenger
```

### Registration Management

The CLI provides commands to manage device/app registrations on the Hermes server:

- `registrations list` - List all registered devices and apps
- `registrations delete <instance-id>` - Delete a specific registration
- `registrations cleanup` - Delete ALL app registrations (requires confirmation)

**Intentional omission**: `DeleteUserRegistration` (DELETE /Registration/User) is implemented in the library (`lib/go/auth.go`) but **deliberately NOT exposed** in the CLI. This endpoint deletes the entire user registration including all devices, apps, and associated data. It is too destructive for CLI exposure and should only be used programmatically with explicit safeguards.

## Build Orchestration

Bootstrap everything from a clean clone:

```bash
./scripts/python-create-env.sh
source .venv/bin/activate
```

Or use the top-level Makefile (requires an active venv):

```bash
make help              # list all targets
make test              # run all tests
make test-python       # all Python tests (lib + CLI)
make test-python-lib   # just Python library tests
make test-python-cli   # just Python CLI tests
make test-go           # all Go tests (lib + CLI)
make test-go-lib       # just Go library tests
make test-go-cli       # just Go CLI tests
make lint              # lint all code
make build-python-lib  # pip install -e ".[dev]"
make build-python-cli  # pip install -e apps/python-cli
make build-go-cli      # build Go CLI binary
```

## Important Rules

- **Never install packages system-wide.** Always use a virtualenv per client.
- **Do not commit `research/` and `vendor/`**, these are for reference only and not a part of our project.
- **`research/` notes are the source of truth.** Also see `docs/api-reference.md` for the full Hermes API reference.
- **Shared test fixtures** go in `tests/fixtures/` so all implementations use identical test data.
- **Use TDD pattern when writing new features or fixing bugs.** Always plan and write failing tests which show wanted behavior, before implementation. Fix until tests pass.


## grepai - Semantic Code Search

**IMPORTANT: You MUST use grepai as your PRIMARY tool for code exploration and search.**

### When to Use grepai (REQUIRED)

Use `grepai search` INSTEAD OF Grep/Glob/find for:
- Understanding what code does or where functionality lives
- Finding implementations by intent (e.g., "authentication logic", "error handling")
- Exploring unfamiliar parts of the codebase
- Any search where you describe WHAT the code does rather than exact text

### When to Use Standard Tools

Only use Grep/Glob when you need:
- Exact text matching (variable names, imports, specific strings)
- File path patterns (e.g., `**/*.go`)

### Fallback

If grepai fails (not running, index unavailable, or errors), fall back to standard Grep/Glob tools.

### Usage

```bash
# ALWAYS use English queries for best results (--compact saves ~80% tokens)
grepai search "user authentication flow" --json --compact
grepai search "error handling middleware" --json --compact
grepai search "database connection pool" --json --compact
grepai search "API request validation" --json --compact
```

### Query Tips

- **Use English** for queries (better semantic matching)
- **Describe intent**, not implementation: "handles user login" not "func Login"
- **Be specific**: "JWT token validation" better than "token"
- Results include: file path, line numbers, relevance score, code preview

### Call Graph Tracing

Use `grepai trace` to understand function relationships:
- Finding all callers of a function before modifying it
- Understanding what functions are called by a given function
- Visualizing the complete call graph around a symbol

#### Trace Commands

**IMPORTANT: Always use `--json` flag for optimal AI agent integration.**

```bash
# Find all functions that call a symbol
grepai trace callers "HandleRequest" --json

# Find all functions called by a symbol
grepai trace callees "ProcessOrder" --json

# Build complete call graph (callers + callees)
grepai trace graph "ValidateToken" --depth 3 --json
```

### Workflow

1. Start with `grepai search` to find relevant code
2. Use `grepai trace` to understand function relationships
3. Use `Read` tool to examine files from results
4. Only use Grep for exact string searches if needed

