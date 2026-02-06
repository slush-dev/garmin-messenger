# Garmin Messenger CLI (Go)

Command-line interface for Garmin Messenger (Hermes) — send, receive, and manage satellite messages from your terminal.

Built on the [Go library](../../lib/go/).

[![Go 1.24+](https://img.shields.io/badge/go-1.24+-00ADD8.svg)](https://go.dev/dl/)

## Install

```bash
cd garmin-messenger

# Build the binary
make build-go-cli    # outputs build/go/garmin-messenger

# Or build directly
cd apps/go-cli
go build -o ../../build/go/garmin-messenger .
```

## Authentication

```bash
# First time — sends an SMS code, then prompts you to enter it
garmin-messenger login --phone "+1234567890"
# Enter SMS OTP code: 123456
# Authenticated! instance=...

# All subsequent commands reuse the saved session (~/.garmin-messenger/)
garmin-messenger conversations
```

## Commands

### conversations

List recent conversations with member names and last message preview.

```bash
garmin-messenger conversations
garmin-messenger conversations --limit 50
garmin-messenger conversations --yaml
```

### messages

Show messages from a conversation.

```bash
garmin-messenger messages CONVERSATION_ID
garmin-messenger messages CONVERSATION_ID --limit 50
garmin-messenger messages CONVERSATION_ID --uuid    # show message/sender UUIDs
```

### send

Send a message with optional GPS location and media attachment.

```bash
# Simple text message
garmin-messenger send --to "+1234567890" --message "Hello from base!"

# With GPS coordinates
garmin-messenger send --to "+1234567890" --message "At camp" \
    --lat 48.8566 --lon 2.3522 --elevation 35.0

# With media attachment (AVIF image or OGG audio)
garmin-messenger send --to "+1234567890" --message "Photo from camp" \
    --file photo.avif
```

### listen

Listen for incoming messages in real time via WebSocket. Press Ctrl+C to stop.

```bash
garmin-messenger listen
garmin-messenger listen --uuid    # show conversation/message/sender UUIDs
garmin-messenger listen --yaml    # YAML output format
```

Automatically marks incoming messages as delivered.

### members

Show members of a conversation with their phone numbers and display names.

```bash
garmin-messenger members CONVERSATION_ID
```

### mute / muted

Mute or unmute conversation notifications. List muted conversations.

```bash
garmin-messenger mute CONVERSATION_ID          # mute
garmin-messenger mute CONVERSATION_ID --off    # unmute
garmin-messenger muted                         # list all muted
```

### sync-contacts

Fetch conversation members from the server and merge into local `contacts.yaml`. This populates friendly names for UUID-based sender identifiers.

```bash
garmin-messenger sync-contacts
garmin-messenger sync-contacts --limit 200   # scan more conversations (default: 100)
```

### device-metadata

Show satellite device metadata (IMEI, device type, satellite message details) for specific messages.

```bash
garmin-messenger device-metadata CONVERSATION_ID MESSAGE_ID_1 MESSAGE_ID_2
```

### network

Show network properties (Iridium satellite network status).

```bash
garmin-messenger network
```

### login

Authenticate via SMS OTP and save the session.

```bash
garmin-messenger login --phone "+1234567890"
garmin-messenger login --phone "+1234567890" --device-name "My Laptop"
```

## Global Options

All commands accept these options:

| Option | Description |
|---|---|
| `--session-dir PATH` | Credential storage directory (default: `~/.garmin-messenger`) |
| `--verbose` / `-v` | Enable debug logging |
| `--yaml` | Output in YAML format (where supported) |

The session directory can also be set via the `GARMIN_SESSION_DIR` environment variable.

## Contact Management

The CLI maintains a local `contacts.yaml` file in the session directory that maps UUIDs to friendly names. This is used to display human-readable sender names instead of raw UUIDs.

```bash
# Populate contacts from server
garmin-messenger sync-contacts

# Contacts are automatically used in conversations, messages, and listen output
garmin-messenger conversations    # shows member names
garmin-messenger listen           # shows sender names
```

The contacts file can also be edited manually to set custom display names.

## Testing

```bash
cd apps/go-cli
go test ./... -v
```
