# Garmin Messenger Plugin for OpenClaw

Channel plugin that connects [OpenClaw](https://github.com/openclaw/openclaw) to Garmin Messenger (Hermes) — let your AI agent send and receive satellite messages.

Built on the [Go CLI](../go-cli/) via MCP stdio.

## Quick Start

```bash
# 1. Install the plugin
openclaw plugins install @slush-openclaw/garmin-messenger

# 2. Add and authenticate (interactive wizard)
openclaw channels add
# Select "Garmin Messenger" from the list — the wizard handles SMS login automatically.
```

To install a specific version:

```bash
openclaw plugins install @slush-openclaw/garmin-messenger@1.0.0
```

<details>
<summary>Alternative: install from GitHub Release tarball</summary>

```bash
curl -LO https://github.com/slush-dev/garmin-messenger/releases/latest/download/garmin-messenger-openclaw-plugin.tgz
openclaw plugins install ./garmin-messenger-openclaw-plugin.tgz
```

</details>

The postinstall script downloads the `garmin-messenger` binary for your platform from the same GitHub release.

## Authentication

### Interactive wizard (recommended)

```bash
openclaw channels add
```

Select Garmin Messenger from the channel list. The wizard prompts for your phone number, sends an SMS verification code, and saves the session.

> **Note:** `openclaw channels add --channel garmin-messenger` uses the non-interactive path — it enables the channel in config but does not start the login wizard. Use the bare `openclaw channels add` for the full setup experience.

### Re-login

```bash
openclaw channels login --channel garmin-messenger
```

Prompts for phone number and SMS code via stdin.

### Agent-driven login

If the channel is enabled but not logged in, the AI agent can authenticate during conversation using the `garmin_login` tool. The agent will ask for your phone number and SMS code.

### Non-interactive (flags only)

```bash
openclaw channels add --channel garmin-messenger --auth-dir ~/.garmin-messenger --cli-path /usr/bin/garmin-messenger
```

Enables the channel without logging in. Authenticate afterwards with `openclaw channels login` or let the agent handle it.

## Configuration

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `binaryPath` | string | auto-detect | Path to `garmin-messenger` binary |
| `sessionDir` | string | `~/.garmin-messenger` | Directory for saved credentials |
| `verbose` | boolean | `false` | Enable debug logging for the MCP binary |
| `dmPolicy` | string | `pairing` | DM policy: `open`, `pairing`, or `allowlist` |
| `allowFrom` | string[] | — | Phone numbers allowed to send messages (allowlist policy) |

### DM Policies

- **open** — accept messages from anyone
- **pairing** — accept messages from existing conversations
- **allowlist** — only accept messages from numbers in `allowFrom`

## How It Works

The plugin spawns the `garmin-messenger mcp` binary as a subprocess and communicates via MCP (Model Context Protocol) over stdio:

1. **Outbound** — OpenClaw calls `send_message` / `send_media_message` MCP tools
2. **Inbound** — the MCP server pushes `notifications/resources/updated` when new messages arrive via FCM
3. **Binary resolution** — checks config path, then bundled `bin/` directory (populated by postinstall), then `PATH`

## Development

```bash
cd apps/openclaw-plugin

# Install dependencies
npm install --ignore-scripts

# Run tests
npm test

# Run tests in watch mode
npm run test:watch

# Build tarball
make build-openclaw-plugin    # outputs build/openclaw-plugin/*.tgz
```

## Project Structure

| File | Purpose |
|------|---------|
| `index.ts` | Plugin entry point — `register(api)` |
| `src/channel.ts` | Channel plugin implementation (gateway, outbound, security, directory, setup, auth) |
| `src/onboarding.ts` | Interactive onboarding wizard for `openclaw channels add` |
| `src/agent-tools.ts` | `garmin_login` agent tool for LLM-driven authentication |
| `src/mcp-bridge.ts` | MCP client wrapper for the Go binary |
| `src/binary.ts` | Binary resolution (config / bundled / PATH) |
| `src/platform.ts` | Shared platform constants and helpers |
| `src/postinstall.ts` | Downloads platform binary from GitHub Releases |
| `src/types.ts` | TypeScript type definitions |
| `openclaw.plugin.json` | Plugin manifest for OpenClaw |
