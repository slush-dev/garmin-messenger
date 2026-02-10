# OpenClaw Channel Plugin Architecture — Reference

> **Last Updated:** 2026-02-08 | **OpenClaw Version:** 2026.2.6-1
>
> This document is a concise reference for building third-party channel plugins.
> It points to original source files instead of duplicating code.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Plugin System](#plugin-system)
3. [Channel Plugin Interface](#channel-plugin-interface)
4. [Context Objects & Adapter Signatures](#context-objects--adapter-signatures)
5. [Inbound Message Processing](#inbound-message-processing)
6. [State Management](#state-management)
7. [IPC Bridge Pattern](#ipc-bridge-pattern)
8. [Installation & Distribution](#installation--distribution)
9. [Testing & Development](#testing--development)
10. [Key Patterns & Pitfalls](#key-patterns--pitfalls)
11. [Garmin Plugin — Alignment Audit](#garmin-messenger-plugin--interface-alignment-audit)
12. [References](#references)

---

## Architecture Overview

```
┌───────────────────────────────────────────────────┐
│                  OpenClaw Core                     │
│  Gateway (WS) ── Agent (LLM) ── Routing           │
│                      │                             │
│               Plugin System (jiti)                 │
└───────────────────────┬───────────────────────────┘
       ┌────────────────┼────────────────┐
  ┌────▼─────┐    ┌─────▼──────┐   ┌─────▼──────┐
  │ Telegram │    │  WhatsApp  │   │  YourApp   │
  │  Plugin  │    │   Plugin   │   │   Plugin   │
  └──────────┘    └────────────┘   └────────────┘
```

**Inbound:** YourApp API → `gateway.startAccount()` → `runtime.processInboundMessage()` → routing → agent

**Outbound:** Agent tool call → `outbound.sendText/sendMedia()` → your API client → YourApp API

---

## Plugin System

### Discovery & Loading

Plugins are scanned in precedence order — first match by ID wins:

1. **Config paths** — `plugins.load.paths` (file or directory)
2. **Workspace extensions** — `<workspace>/.openclaw/extensions/*.ts`
3. **Global extensions** — `~/.openclaw/extensions/*.ts`
4. **Bundled extensions** — `<openclaw>/extensions/*` (disabled by default)

Plugins load at runtime via **jiti** (TS/JS dynamic loader).
See: `src/plugins/loader.ts:211`

This means:
- Entry point (`index.ts`) must be TypeScript/JavaScript
- Plugin runs **in-process** with the gateway (Node.js)
- No compilation step needed during development

---

## Channel Plugin Interface

### Core Type

**Defined in:** `src/channels/plugins/types.plugin.ts`

`ChannelPlugin<ResolvedAccount, Probe, Audit>` has these fields:

| Field | Required | Purpose |
|-------|----------|---------|
| `id` | **yes** | Unique channel identifier (`ChannelId`) |
| `meta` | **yes** | Display info: `label`, `selectionLabel`, `docsPath`, `blurb`, `icon` |
| `capabilities` | **yes** | Feature flags: `chatTypes`, `media`, `reactions`, `polls`, `edit`, `unsend`, `reply` |
| `config` | **yes** | Account management (`listAccountIds`, `resolveAccount`, `isConfigured`, `describeAccount`) |
| `outbound` | recommended | Message sending (`sendText`, `sendMedia`, `sendPoll`, `deliveryMode`, `chunker*`) |
| `gateway` | recommended | Connection lifecycle (`startAccount`, `stopAccount`, `loginWithQr*`, `logoutAccount`) |
| `security` | recommended | DM/group policies (`resolveDmPolicy`, `collectWarnings`) |
| `status` | optional | Health checks (`probeAccount`, `buildAccountSnapshot`, `collectStatusIssues`) |
| `setup` | optional | CLI onboarding (`resolveAccountId`, `applyAccountConfig`, `validateInput`) |
| `pairing` | optional | User approval flow (`idLabel`, `normalizeAllowEntry`, `notifyApproval`) |
| `groups` | optional | Group handling (`resolveRequireMention`, `resolveToolPolicy`) |
| `threading` | optional | Thread support (`resolveReplyToMode`, `buildToolContext`) |
| `messaging` | optional | Target normalization (`normalizeTarget`, `targetResolver`) |
| `directory` | optional | Contact/group lists (`self`, `listPeers`, `listPeersLive`, `listGroups*`) |
| `actions` | optional | Buttons/reactions (`supportsAction`, `handleAction`) |
| `mentions` | optional | Mention stripping (`stripPatterns`, `stripMentions`) |
| `agentPrompt` | optional | LLM instructions (`messageToolHints`) |
| `agentTools` | optional | Custom tools visible to the LLM |
| `auth` | optional | General auth adapter |
| `elevated` | optional | Elevated permissions |
| `commands` | optional | Custom commands |
| `streaming` | optional | Streaming text support |
| `heartbeat` | optional | Heartbeat/keepalive |
| `resolver` | optional | ID resolution (`resolveTargets`) |
| `reload` | optional | Config paths that trigger gateway restart |
| `defaults` | optional | Default settings (e.g. `queue.debounceMs`) |
| `configSchema` | optional | JSON schema for config validation |

**Full type definitions:**
- Adapter interfaces: `src/channels/plugins/types.adapters.ts`
- Core types: `src/channels/plugins/types.core.ts`
- SDK exports: `src/plugin-sdk/index.ts`

---

## Context Objects & Adapter Signatures

All adapter types are defined in `src/channels/plugins/types.adapters.ts`.

### `ChannelGatewayContext<ResolvedAccount>`

Used by `gateway.startAccount()` / `stopAccount()`:

| Field | Type | Purpose |
|-------|------|---------|
| `cfg` | `OpenClawConfig` | Full config |
| `accountId` | `string` | Account identifier |
| `account` | `ResolvedAccount` | Your resolved account type |
| `runtime` | `RuntimeEnv` | Core utilities (see below) |
| `abortSignal` | `AbortSignal` | Listen for graceful shutdown |
| `log` | `ChannelLogSink?` | `.info()`, `.warn()`, `.error()` |
| `getStatus()` | → `ChannelAccountSnapshot` | Read current status |
| `setStatus()` | `(next) → void` | Update status |

### `ChannelOutboundContext`

Used by `outbound.sendText()` / `sendMedia()`:

| Field | Type | Purpose |
|-------|------|---------|
| `cfg` | `OpenClawConfig` | Full config |
| `to` | `string` | Target ID (normalized) |
| `text` | `string` | Message text |
| `mediaUrl` | `string?` | Media URL (for sendMedia) |
| `replyToId` | `string?` | Reply-to message ID |
| `threadId` | `string \| number?` | Thread/topic ID |
| `accountId` | `string?` | Which account to send from |
| `deps` | `OutboundSendDeps?` | Dependency injection |

**Returns:** `OutboundDeliveryResult` — `{ channel, messageId, chatId?, timestamp?, meta? }`
(Defined in `src/infra/outbound/deliver.ts`)

### `ChannelSecurityContext<ResolvedAccount>`

Used by `security.resolveDmPolicy()`:

| Field | Type |
|-------|------|
| `cfg` | `OpenClawConfig` |
| `accountId` | `string?` |
| `account` | `ResolvedAccount` |

**Returns:** `ChannelSecurityDmPolicy` — `{ policy, allowFrom[], policyPath, allowFromPath, approveHint?, normalizeEntry? }`

### `ChannelAccountSnapshot`

Defined in `src/channels/plugins/types.core.ts:95`. Key fields:
`accountId`, `running`, `connected`, `enabled`, `configured`, `linked`, `lastConnectedAt`, `lastDisconnect`, `lastMessageAt`, `lastError`, `reconnectAttempts`

### `PluginRuntime`

Defined in `src/plugins/runtime/types.ts`. Massive namespace providing:
- `config.*` — loadConfig, writeConfigFile
- `system.*` — enqueueSystemEvent, runCommandWithTimeout
- `media.*` — loadWebMedia, detectMime, imageOps
- `channel.text.*` — chunk, stripMarkdown, formatMention
- `channel.reply.*`, `channel.routing.*`, `channel.pairing.*`, `channel.media.*`
- `logging.*` — shouldLogVerbose, getChildLogger

---

## Inbound Message Processing

### `MsgContext`

When receiving a message, build a `MsgContext` and call `ctx.runtime.processInboundMessage()`.

**Core required fields:**

| Field | Purpose |
|-------|---------|
| `Body` | Message text (after mention stripping) |
| `From` | Sender ID (normalized) |
| `SessionKey` | Unique session ID — `{channel}:{accountId}:{userId}` for DMs, `{channel}:{accountId}:group:{groupId}` for groups |
| `AccountId` | Which account received this |

**Important optional fields:**
`MessageSid`, `SenderName`, `SenderUsername`, `Provider`, `ChatType` (`"direct"` or `"group"`), `GroupId`, `GroupSubject`, `WasMentioned`, `MediaPath`, `MediaUrl`, `MediaType`, `ReplyToId`

Full interface: `src/channels/plugins/types.core.ts` (imported from auto-reply module)

### Key Rules

1. **Always set `SessionKey`** — it identifies the conversation for routing
2. **Set `ChatType` correctly** — affects routing and group mention logic
3. **Set `WasMentioned`** in groups when bot was @mentioned
4. **For media:** pass `MediaUrl` for remote URLs, or save to `~/.openclaw/media/` and pass `MediaPath`

---

## State Management

### Storage Locations

| Location | Persistence | Use For |
|----------|------------|---------|
| `getStatus()`/`setStatus()` | Volatile (RAM) | Connection state, counters, timestamps |
| `runtime.config.*` | Persistent (`~/.openclaw/config.json`) | Tokens, preferences, sync cursors |
| `~/.openclaw/sessions/` | Persistent (auto-managed) | Conversation history (don't touch) |
| `~/.openclaw/media/` | Temporary (auto-cleaned ~2min) | Downloaded media |
| `~/.openclaw/plugins/{id}/` | Persistent (custom) | Plugin-specific queues, caches |

### Lifecycle Pattern

1. In `gateway.startAccount()`: load persistent state, set status `running: true`
2. On messages: update `lastMessageAt`, persist periodically
3. On `abortSignal` "abort" event: save final state, set `running: false, connected: false`

---

## IPC Bridge Pattern

The plugin API requires TypeScript (loaded via jiti, runs in-process). For non-JS core logic, use an IPC bridge:

```
OpenClaw Gateway (Node.js)
  └─ Your Plugin (TypeScript: index.ts, channel.ts, bridge.ts)
       └─ IPC (stdin/stdout or HTTP)
            └─ Your Core App (Python/Go/Rust)
```

**Existing examples of IPC bridges:**
- `extensions/zalouser/src/zca.ts` — spawns CLI binary via `child_process.spawn()`
- `extensions/bluebubbles/` — HTTP API client

| Approach | Best For |
|----------|----------|
| Pure TypeScript | Fastest, simplest; use when JS SDK available |
| stdin/stdout JSON | Quick integration with any language |
| HTTP sidecar | Production; better crash isolation |

Our Garmin plugin uses **MCP over stdin/stdout** (`@modelcontextprotocol/sdk StdioClientTransport`) to bridge to the Go binary.

---

## Installation & Distribution

### Plugin Files Required

```
your-plugin/
├── index.ts                 # Entry: export default { id, register(api) }
├── openclaw.plugin.json     # Manifest: id, channels[], configSchema, uiHints
├── package.json             # openclaw.extensions, openclaw.channel fields
└── src/
    ├── channel.ts           # ChannelPlugin implementation
    └── runtime.ts           # Runtime bridge (setRuntime/getRuntime)
```

**Manifest** (`openclaw.plugin.json`): validated without executing plugin code. Declares channel IDs, JSON schema for config, UI hints for sensitive fields.

**Entry point** (`index.ts`): must call `setRuntime(api.runtime)` then `api.registerChannel({ plugin })`.

**See working examples:** `extensions/nostr/` (simple DM-only), `extensions/matrix/` (full-featured, 66 files), `extensions/bluebubbles/` (HTTP bridge)

### Installation Methods

```bash
# npm (recommended for public distribution)
openclaw plugins install @yourorg/openclaw-yourapp

# GitHub tarball (download first — CLI does not support URLs)
curl -LO https://github.com/org/repo/releases/download/v1.0.0/plugin.tgz
openclaw plugins install ./plugin.tgz

# GitHub subdirectory (npm 7+)
openclaw plugins install "github:org/repo#main:packages/yourapp"

# Local development (live reload)
openclaw plugins install -l ./path/to/extension

# Config-based
# In ~/.openclaw/config.json: { "plugins": { "load": { "paths": ["/path/to/ext"] } } }
```

---

## Testing & Development

### Test Pyramid

1. **Unit tests (vitest):** `pnpm test extensions/yourapp` — config, normalization, parsing
2. **Gateway integration:** `pnpm gateway:dev` + `pnpm openclaw message send --channel yourapp --to user --message "hi"`
3. **Manual:** configure in `~/.openclaw/config.json`, send real messages
4. **Live (optional):** `YOURAPP_LIVE_TEST=1 pnpm test:live extensions/yourapp`

### Key CLI Commands

```bash
pnpm openclaw plugins list --verbose     # List loaded plugins
pnpm openclaw plugins info yourapp       # Plugin details
pnpm openclaw config validate            # Validate config
pnpm openclaw channels status --probe    # Health check
pnpm openclaw doctor                     # Full diagnostic
DEBUG=openclaw:* pnpm openclaw gateway run  # Verbose logging
```

### Dev Loop

```bash
vim extensions/yourapp/src/channel.ts    # Edit
pnpm test extensions/yourapp             # Unit tests
pnpm openclaw gateway restart            # Reload
pnpm openclaw message send ...           # Test
```

Or use `pnpm gateway:watch` for auto-restart on save.

---

## Key Patterns & Pitfalls

### Critical Patterns

**1. Always bridge runtime first in `register()`:**
```typescript
register(api: OpenClawPluginApi) {
  setRuntime(api.runtime);              // MUST be first
  api.registerChannel({ plugin });
}
```

**2. Always handle AbortSignal for cleanup:**
```typescript
gateway: {
  startAccount: async (ctx) => {
    const timer = setInterval(() => { /* poll */ }, 5000);
    ctx.abortSignal.addEventListener("abort", () => clearInterval(timer));
  },
}
```

**3. Always wrap message handlers in try/catch:**
```typescript
onMessage: async (msg) => {
  try {
    await ctx.runtime.processInboundMessage({ Body: msg.text, ... });
  } catch (err) {
    ctx.log?.error(`Failed: ${err}`);  // Don't rethrow — one bad msg shouldn't crash
  }
}
```

**4. Return immediately from `startAccount()`** — use `setInterval` or event listeners, not `while` loops that block the event loop.

**5. Delivery mode choice:**

| Mode | Use When |
|------|----------|
| `direct` | Stateless HTTP APIs, low latency |
| `gateway` | WebSocket/long-lived connections (needs shared connection state) |
| `hybrid` | Direct for DMs, gateway for groups |

### Common Mistakes

| Mistake | Fix |
|---------|-----|
| Missing `SessionKey` in `processInboundMessage()` | Always provide `{channel}:{accountId}:{userId}` |
| `workspace:*` in `dependencies` (not `devDependencies`) | Move to `devDependencies` + `peerDependencies` |
| Not checking `abortSignal.aborted` in polling | Check before each iteration; clean up on abort |
| Throwing in message handlers | Wrap in try/catch, log and continue |
| Unbounded `Map` for caching | Use TTL or max-size eviction |

### Reconnection

Use exponential backoff with a max attempt count. Check `ctx.abortSignal.aborted` before reconnecting (abort = intentional shutdown, don't reconnect). Update `ctx.setStatus()` with `connected`, `reconnectAttempts`, `lastError` on each state change.

### Debouncing

Use `createInboundDebouncer` from `openclaw/runtime` to batch rapid messages (reduces agent invocations ~70%). Configure: `debounceMs`, `buildKey`, `shouldDebounce` (skip commands/media), `onFlush`.

### agentPrompt Hints

Return `string[]` from `agentPrompt.messageToolHints()`. These are injected into the LLM system prompt when your channel is active. Use for: message length limits, supported formatting, special directives (polls, cards).
See LINE example: `extensions/line/src/channel.ts`

---

## Garmin Messenger Plugin — Interface Alignment Audit

> **Date:** 2026-02-08

The Garmin Messenger plugin (`apps/openclaw-plugin/`) defines custom type aliases
in `src/types.ts` that do **not** match the real `ChannelPlugin` contract. The
plugin was never compiled against `openclaw/plugin-sdk` (distributed independently),
so the mismatch was invisible at compile time.

### Required Fields — Status

| Field | OpenClaw Type | Our Plugin | Status |
|-------|--------------|------------|--------|
| `id` | `ChannelId` | added 2026-02-08 | Fixed |
| `meta` | `ChannelMeta` (label, docsPath, blurb, ...) | **missing** | Needs impl |
| `capabilities` | `ChannelCapabilities` (chatTypes, media, ...) | **missing** | Needs impl |
| `config` | `ChannelConfigAdapter` (listAccountIds, resolveAccount, ...) | **wrong type** — ours is plugin settings (binaryPath, sessionDir) | Needs rewrite |

### Adapter Signature Mismatches

| Adapter | OpenClaw | Ours |
|---------|----------|------|
| `gateway.startAccount` | `(ctx: ChannelGatewayContext) → Promise<unknown>` | `(accountId, config) → Promise<void>` |
| `gateway.stopAccount` | `(ctx: ChannelGatewayContext) → Promise<void>` | `(accountId) → Promise<void>` |
| `outbound.sendText` | `(ctx: ChannelOutboundContext) → Promise<OutboundDeliveryResult>` | `(accountId, to, body) → Promise<OutboundResult>` |
| `outbound.sendMedia` | `(ctx: ChannelOutboundContext) → Promise<OutboundDeliveryResult>` | `(accountId, to, body, filePath, mediaType?) → Promise<OutboundResult>` |
| `security.resolveDmPolicy` | `(ctx: ChannelSecurityContext) → DmPolicy \| null` | `(accountId, senderId) → Promise<DmPolicyResult>` |
| `status.probeAccount` | `({account, timeoutMs, cfg}) → Promise<Probe>` | `(accountId) → Promise<AccountStatus>` |

### Return Type Mismatches

| Adapter | OpenClaw | Ours |
|---------|----------|------|
| `outbound.send*` | `OutboundDeliveryResult` (`channel`, `messageId`, `chatId?`, `timestamp?`, `meta?`) | `OutboundResult` (`ok`, `messageId?`, `conversationId?`, `error?`) |
| `security.resolveDmPolicy` | `ChannelSecurityDmPolicy` (`policy`, `allowFrom[]`, `policyPath`, `allowFromPath`) | `DmPolicyResult` (`allowed`, `reason?`) |

### Missing Adapters

- `config.listAccountIds(cfg)` — OpenClaw needs this to discover accounts
- `config.resolveAccount(cfg, accountId)` — returns `ResolvedAccount`
- `config.isConfigured(account, cfg)` — config validation
- `config.describeAccount(account, cfg)` — status snapshot

### Login Flow

OpenClaw's `ChannelGatewayAdapter` provides `loginWithQrStart`/`loginWithQrWait` for QR-code flows. No built-in OTP pattern. Options for our SMS OTP:

1. **`agentTools`** — custom channel tools visible to the LLM (best fit)
2. **`auth.login()`** — general-purpose CLI auth entry point
3. **Custom gateway methods** — requires OpenClaw to not reject unknown keys

### What Works Today

Only `registerChannel({ plugin })` + the `id` field. The gateway stores the plugin but **cannot call any adapter** because signatures don't match.

### Fix Strategy

Rewrite `src/types.ts` to conform to `ChannelPlugin<ResolvedAccount>` from `openclaw/plugin-sdk`. Use `extensions/nostr/` or `extensions/bluebubbles/` as templates. Keep MCPBridge layer unchanged — only the adapter surface facing OpenClaw needs to change.

---

## References

### Key Source Files

| File | Contains |
|------|----------|
| `src/channels/plugins/types.plugin.ts` | `ChannelPlugin` type definition |
| `src/channels/plugins/types.adapters.ts` | All adapter interfaces (`ChannelGatewayAdapter`, `ChannelOutboundAdapter`, `ChannelSecurityAdapter`, etc.) and context types (`ChannelGatewayContext`, `ChannelOutboundContext`) |
| `src/channels/plugins/types.core.ts` | `ChannelAccountSnapshot`, `ChannelMeta`, `ChannelCapabilities`, `ChannelSecurityContext`, `MsgContext` |
| `src/plugin-sdk/index.ts` | Public SDK exports (all Channel* types, helpers, utilities) |
| `src/plugins/loader.ts` | Plugin loading via jiti |
| `src/plugins/types.ts` | Plugin API types (`OpenClawPluginApi`, `OpenClawPluginModule`) |
| `src/plugins/runtime/types.ts` | `PluginRuntime` — full runtime API (config, media, channel utils, logging) |
| `src/infra/outbound/deliver.ts` | `OutboundDeliveryResult` |
| `src/agents/system-prompt.ts` | How `agentPrompt.messageToolHints` reaches the LLM |

### Example Plugin Implementations

| Plugin | Style | Complexity | Key Pattern |
|--------|-------|-----------|-------------|
| `extensions/nostr/` | DM-only | Simple (21 files) | Minimal channel |
| `extensions/matrix/` | Full-featured | Large (66 files) | All adapters |
| `extensions/telegram/` | Core-delegated | Minimal (2 files) | Thin wrapper |
| `extensions/line/` | Rich messages | Medium (5 files) | agentPrompt hints |
| `extensions/zalouser/` | IPC bridge | Medium (14 files) | `child_process.spawn()` |
| `extensions/bluebubbles/` | HTTP bridge | Medium (22 files) | HTTP API client |

### External Documentation

- Plugin system: https://docs.openclaw.ai/plugin
- Channel integration: https://docs.openclaw.ai/channels
- Plugin manifest: https://docs.openclaw.ai/plugins/manifest

---

**End of Document**
