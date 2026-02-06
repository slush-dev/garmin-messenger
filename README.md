# Garmin Messenger Client

**Unofficial Garmin Messenger API client for communicating with InReach satellite devices — no hardware required.**

Send and receive messages to Garmin InReach satellite messengers over the internet using just a Garmin Messenger account and a phone number.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

---

## What Is This?

Garmin Messenger is a mobile app that lets you exchange text messages with Garmin InReach satellite devices (inReach Mini 2, inReach Messenger, GPSMAP 67i, Montana 700i, etc.) over the internet. This project implements the same messaging protocol as the official app, allowing you to:

- **Send messages** to InReach devices anywhere on Earth via satellite
- **Receive messages** in real-time from InReach devices via WebSocket
- **List conversations** and message history
- **Track message delivery status** (sent, delivered, read)
- **Manage conversations** (mute/unmute, block/unblock users)
- **Access location data** shared by InReach devices (GPS coordinates, elevation, speed, heading)

All you need is a phone number registered with Garmin Messenger. No InReach device or Garmin hardware is required on your end.

## Use Cases

- **Home base communication** — Build a desktop or web dashboard for two-way messaging with field teams carrying InReach devices
- **Automated dispatching** — Send automated messages, alerts, or check-ins to satellite devices from your backend
- **Integration with other platforms** — Bridge Garmin Messenger to Slack, Telegram, Discord, email, or SMS
- **Fleet tracking** — Monitor location data and messages from multiple InReach devices programmatically
- **Emergency response** — Build custom alerting systems that receive and forward SOS-adjacent communications
- **IoT and telemetry** — Receive sensor data or status reports from remote InReach-equipped stations

## Repository Structure

```
├── clients/                 Client library implementations
│   └── python/              Python client library (complete, 231 tests)
├── apps/                    Standalone applications
│   └── cli/                 CLI tool (complete, 263 tests)
├── tests/                   Cross-implementation test infrastructure
│   └── fixtures/            Shared mock API response data (17 JSON files)
├── docs/                    Protocol & API documentation
└── tools/                   Development tooling
```

## Client Implementations

| Language | Directory | Status | README |
|---|---|---|---|
| Python | [`clients/python/`](clients/python/) | Complete | **[Python Client README](clients/python/README.md)** |
| Go | `clients/go/` | Planned | — |
| Rust | `clients/rust/` | Planned | — |
| C | `clients/c/` | Planned | — |

## Applications

| App | Directory | Description |
|---|---|---|
| CLI | [`apps/cli/`](apps/cli/) | Full-featured command-line tool — **[CLI README](apps/cli/README.md)** |

> Want to add an implementation or application? Contributions are welcome — see [Contributing](#contributing).

## Quick Start

### CLI (fastest)

```bash
pip install -e clients/python && pip install -e apps/cli

garmin-messenger login --phone "+1234567890"
garmin-messenger conversations
garmin-messenger send --to "+1234567890" --message "Hello from base!"
garmin-messenger listen
```

### Python library

See [clients/python/README.md](clients/python/README.md) for library usage examples.

## Authentication Flow

All implementations use the same SMS OTP (one-time password) authentication flow, matching the official Garmin Messenger app:

1. You provide your phone number registered with Garmin Messenger
2. The client sends a registration request to the Hermes API
3. Garmin sends a 6-digit verification code via SMS to your phone
4. You enter the code to complete authentication
5. The server returns an access token, refresh token, and instance ID
6. Credentials are saved locally (`~/.garmin-messenger/`) for reuse

Tokens are automatically refreshed when they expire. Sessions persist across restarts.

## Protocol Reference

Base URL: `https://hermes.inreachapp.com`

For the full API reference with request/response examples, see **[docs/api-reference.md](docs/api-reference.md)**.

### REST API Overview

| Area | Endpoints | Description |
|---|---|---|
| Registration | `/Registration/App`, `/App/Confirm`, `/App/Refresh` | SMS OTP auth and token management |
| Conversations | `/Conversation/Updated`, `/Conversation/Details/{id}`, `/Conversation/Members/{id}`, `/Conversation/Muted` | List, inspect, and manage conversations |
| Messages | `/Message/Send`, `/Message/DeviceMetadata`, `/Message/Media/*` | Send messages, media attachments, satellite device info |
| Status | `/Status/Read`, `/Status/Delivered`, `/Status/Update`, `/Status/Updated` | Read receipts, batch updates |
| User Info | `/UserInfo/Capabilities`, `/UserInfo/Block` | Account capabilities, block/unblock |
| Network | `/NetworkInfo/Properties` | Iridium satellite network status |

### SignalR WebSocket

Hub path: `/messaging`

Real-time events: `ReceiveMessage`, `ReceiveMessageUpdate`, `ReceiveConversationMuteStatusUpdate`, `ReceiveUserBlockStatusUpdate`, `ReceiveServerNotification`, `ReceiveNonconversationalMessage`

Client invocations: `MarkAsDelivered`, `MarkAsRead`, `NetworkProperties`

## Development

```bash
# Run all tests
make test

# Lint all code
make lint

# Run only Python tests
make test-python

# Install Python client in dev mode
make build-python

# See all targets
make help
```

## Requirements

- A phone number registered with the [Garmin Messenger](https://www.garmin.com/en-US/p/882559) app
- Internet connection
- No Garmin hardware required on the client side

For implementation-specific requirements, see the respective README.

## FAQ

**Do I need an InReach device?**
No. You only need a Garmin Messenger account (free app, registered with a phone number). The person you're communicating with uses the InReach device.

**What InReach devices are supported?**
Any device compatible with Garmin Messenger: inReach Mini 2, inReach Messenger, GPSMAP 66i/67i, Montana 700i/750i, Overlander, and others.

**Is this the same as the Garmin/Explore API?**
No. This uses the Garmin Messenger (Hermes) protocol, which is the backend for the Garmin Messenger mobile app. It is separate from the Garmin Connect or Explore APIs.

**Can I use this for group conversations?**
Yes. The API supports multi-member conversations. Send messages to multiple recipients by passing multiple phone numbers.

**How does authentication work?**
Same as the official app: SMS-based one-time password. You get a text message with a 6-digit code each time you register a new session.

**Do sessions expire?**
Access tokens expire but are automatically refreshed using the stored refresh token. Sessions persist across restarts as long as the saved credentials file exists.

**Can I send messages to phone numbers (not InReach devices)?**
Yes. Garmin Messenger supports messaging between app users (phone-to-phone) and between app users and InReach devices.

## Contributing

Contributions are welcome! Particularly:

- **New language implementations** — Go, Rust, C, TypeScript/Node.js
- **Applications** — CLI tools, chat bots, bridges to other platforms
- **Documentation** — Improvements to API docs, examples, and guides
- **Test infrastructure** — Conformance tests, mock server, fixtures

Please open an issue first to discuss significant changes.

## Disclaimer

This is an unofficial, community-built client. It is not affiliated with, endorsed by, or supported by Garmin Ltd. Use at your own risk. Garmin may change their API at any time, which could break this client.

## License

[MIT](LICENSE)

---

**Keywords:** Garmin Messenger API, Garmin InReach API client, InReach satellite messenger, send message to InReach, Garmin Messenger Python library, InReach two-way messaging, Garmin satellite communication SDK, InReach Mini 2 API, Garmin Messenger protocol, Hermes API, satellite messenger integration, InReach automation, Garmin Messenger bot, InReach REST API, Garmin Messenger WebSocket, Garmin inReach SDK
