import { homedir } from "node:os";
import { join } from "node:path";
import { mkdir } from "node:fs/promises";
import { createInterface } from "node:readline";
import { MCPBridge } from "./mcp-bridge.js";
import { resolveBinary } from "./binary.js";
import { getGarminRuntime } from "./runtime.js";
import { debugLog } from "./debug.js";
import { garminOnboardingAdapter } from "./onboarding.js";
import { createGarminAgentTools, setAccountsRef } from "./agent-tools.js";
import type {
  ChannelPlugin,
  ChannelGatewayContext,
  ChannelOutboundContext,
  ChannelAccountSnapshot,
  OutboundDeliveryResult,
  OtpRequestResult,
  OtpConfirmResult,
  DirectoryPeer,
  ResolvedGarminAccount,
  OpenClawConfig,
  RuntimeLogger,
  GarminStatus,
  GarminContacts,
  GarminMessage,
  GarminUserLocation,
} from "./types.js";
import { DEFAULT_ACCOUNT_ID } from "./types.js";

export { debugLog } from "./debug.js";

// Per-account state (internal)
interface AccountState {
  bridge: MCPBridge;
  account: ResolvedGarminAccount;
  binaryPath?: string;
  instanceId?: string;
  knownSenders: Set<string>;
}

// Use Symbol.for so state is shared even if module is loaded multiple times (e.g. by jiti)
const ACCOUNTS_KEY = Symbol.for("openclaw-garmin-messenger-accounts");
const accounts: Map<string, AccountState> =
  (globalThis as any)[ACCOUNTS_KEY] ??= new Map<string, AccountState>();

// Share accounts ref with agent-tools module
setAccountsRef(accounts as any);

function getAccount(accountId: string): AccountState {
  const state = accounts.get(accountId);
  if (!state) throw new Error(`Account ${accountId} not started`);
  return state;
}

/** Reset module state for tests. */
export function _resetForTesting(): void {
  accounts.clear();
  (globalThis as any)[ACCOUNTS_KEY] = accounts;
}

function defaultSessionDir(): string {
  return join(homedir(), ".garmin-messenger");
}

/** Start listening + subscribe after a successful login. Shared by gateway and agent tool. */
async function performPostLoginSetup(state: AccountState, accountId: string): Promise<void> {
  let log: RuntimeLogger | undefined;
  try { log = getGarminRuntime().logging.getChildLogger({ channel: "garmin-messenger" }); } catch {}

  const listenResult = await state.bridge.startListening();
  if (listenResult.isError) {
    log?.error(`Failed to start listening after login: ${listenResult.text}`);
  } else {
    log?.info(`Account ${accountId}: listening for messages`);
    try {
      await state.bridge.subscribe("garmin://messages");
    } catch (err) {
      log?.warn(`Failed to subscribe to message notifications: ${err}`);
    }
  }
}

async function startAccountInner(ctx: ChannelGatewayContext<ResolvedGarminAccount>): Promise<void> {
  const { accountId, account, log, abortSignal } = ctx;

  // Stop existing account if already running
  if (accounts.has(accountId)) {
    log?.warn(`Account ${accountId} already started, stopping first`);
    const prev = accounts.get(accountId)!;
    try {
      if (prev.bridge.connected) {
        await prev.bridge.stopListening();
        await prev.bridge.disconnect();
      }
    } catch (err) {
      log?.warn(`Error stopping previous account: ${err}`);
    }
    accounts.delete(accountId);
  }

  const binaryPath = resolveBinary(account.config.binaryPath);
  debugLog(`resolved binary: ${binaryPath}`);

  const bridge = new MCPBridge({
    binaryPath,
    sessionDir: account.config.sessionDir,
    verbose: account.config.verbose,
    logger: log ?? { info() {}, warn() {}, error() {} },
    onResourceUpdated: (uri: string, meta?: Record<string, unknown>) => {
      debugLog(`[inbound] resource update notification: ${uri} meta=${JSON.stringify(meta)}`);
      // Fire-and-forget: minimal state mutation here; message ordering is
      // handled by the AI agent layer, so async dispatch is acceptable.
      handleResourceUpdate(accountId, uri, meta).catch((err) => {
        debugLog(`[inbound] ERROR handling resource update: ${err}\n${(err as Error).stack ?? ""}`);
        log?.error(`Error handling resource update: ${err}`);
      });
    },
    onDisconnected: () => {
      log?.error(`Account ${accountId}: MCP bridge disconnected unexpectedly`);
    },
  });

  const state: AccountState = {
    bridge,
    account,
    binaryPath,
    knownSenders: new Set(),
  };
  accounts.set(accountId, state);

  debugLog(`startAccount: connecting MCP bridge...`);
  await bridge.connect();
  debugLog(`startAccount: MCP bridge connected`);

  ctx.setStatus({
    ...ctx.getStatus(),
    running: true,
    connected: true,
    lastConnectedAt: Date.now(),
    lastError: null,
  });

  // Check login status
  debugLog(`startAccount: checking login status...`);
  const status = await bridge.getStatus();
  debugLog(`startAccount: status = ${JSON.stringify(status)}`);
  if (!status.logged_in) {
    log?.warn(`Account ${accountId}: not logged in — run 'garmin-messenger login' first`);
    debugLog(`startAccount: NOT LOGGED IN, returning early`);
    return;
  }

  state.instanceId = status.instance_id;
  debugLog(`startAccount: instanceId=${status.instance_id}`);
  ctx.setStatus({ ...ctx.getStatus(), linked: true });

  // Start listening for real-time messages
  debugLog(`startAccount: calling startListening...`);
  const result = await bridge.startListening();
  if (result.isError) {
    debugLog(`startAccount: startListening FAILED: ${result.text}`);
    log?.error(`Failed to start listening: ${result.text}`);
  } else {
    debugLog(`startAccount: listening OK — ${result.text}`);
    log?.info(`Account ${accountId}: listening for messages`);

    // Subscribe to the sentinel URI so the server delivers notifications to us
    try {
      await bridge.subscribe("garmin://messages");
      debugLog(`startAccount: subscribed to garmin://messages`);
    } catch (err) {
      debugLog(`startAccount: subscribe FAILED: ${err}`);
      log?.warn(`Failed to subscribe to message notifications: ${err}`);
    }
  }

  // Cleanup on abort
  abortSignal.addEventListener("abort", () => {
    debugLog(`startAccount: abort signal received for ${accountId}`);
    const s = accounts.get(accountId);
    if (s?.bridge.connected) {
      s.bridge.stopListening().catch(() => {});
      s.bridge.disconnect().catch(() => {});
    }
    accounts.delete(accountId);
    ctx.setStatus({ ...ctx.getStatus(), running: false, connected: false });
  });
}

// Custom gateway methods not in the SDK's ChannelGatewayAdapter — OpenClaw
// ignores unknown adapter keys, so they're safe to add here.
type GarminGatewayExtensions = {
  gateway?: {
    loginWithOtpRequest?: (accountId: string, phone: string, deviceName?: string) => Promise<OtpRequestResult>;
    loginWithOtpConfirm?: (accountId: string, phone: string, requestId: string, otpCode: string) => Promise<OtpConfirmResult>;
  };
};

export const garminPlugin: ChannelPlugin<ResolvedGarminAccount> & GarminGatewayExtensions = {
  id: "openclaw-garmin-messenger",

  meta: {
    id: "openclaw-garmin-messenger",
    label: "Garmin Messenger",
    selectionLabel: "Garmin Messenger",
    docsPath: "/channels/garmin-messenger",
    blurb: "Send and receive messages via Garmin Messenger (Hermes protocol)",
    quickstartAllowFrom: true,
  },

  capabilities: {
    chatTypes: ["direct"],
    media: true,
    reactions: false,
    polls: false,
    edit: false,
    unsend: false,
    reply: false,
  },

  configSchema: {
    schema: {
      type: "object",
      additionalProperties: false,
      properties: {
        enabled: { type: "boolean" },
        binaryPath: { type: "string" },
        sessionDir: { type: "string" },
        verbose: { type: "boolean" },
        dmPolicy: { type: "string", enum: ["open", "pairing", "allowlist"] },
        allowFrom: { type: "array", items: { type: "string" } },
      },
    },
    uiHints: {
      enabled: {
        label: "Enabled",
        help: "Enable or disable the Garmin Messenger channel",
      },
      binaryPath: {
        label: "Binary Path",
        placeholder: "/usr/local/bin/garmin-messenger",
        help: "Path to the garmin-messenger binary (auto-detected from bundled bin/ or PATH if omitted)",
        advanced: true,
      },
      sessionDir: {
        label: "Session Directory",
        placeholder: "~/.garmin-messenger",
        help: "Directory to store session credentials",
        advanced: true,
      },
      verbose: {
        label: "Verbose Logging",
        help: "Enable debug logging for the MCP server process",
        advanced: true,
      },
      dmPolicy: {
        label: "DM Policy",
        help: "'open' allows anyone, 'pairing' requires approval, 'allowlist' restricts to allowed numbers",
      },
      allowFrom: {
        label: "Allow From",
        placeholder: "+1234567890",
        help: "Phone numbers allowed to message (used with 'allowlist' or 'pairing' policy)",
      },
    },
  },

  reload: {
    configPrefixes: ["channels.garmin-messenger"],
  },

  config: {
    listAccountIds(cfg: OpenClawConfig): string[] {
      const ch = cfg.channels?.["garmin-messenger"];
      if (!ch?.enabled) return [];
      return [DEFAULT_ACCOUNT_ID];
    },

    resolveAccount(cfg: OpenClawConfig, accountId?: string | null): ResolvedGarminAccount {
      const ch = cfg.channels?.["garmin-messenger"] ?? {};
      return {
        accountId: accountId ?? DEFAULT_ACCOUNT_ID,
        enabled: ch.enabled ?? false,
        config: {
          binaryPath: ch.binaryPath,
          sessionDir: ch.sessionDir,
          verbose: ch.verbose,
          dmPolicy: ch.dmPolicy,
          allowFrom: ch.allowFrom,
        },
      };
    },

    describeAccount(account: ResolvedGarminAccount, _cfg: OpenClawConfig): ChannelAccountSnapshot {
      const state = accounts.get(account.accountId);
      let configured = false;
      try {
        resolveBinary(account.config.binaryPath);
        configured = true;
      } catch {}
      return {
        accountId: account.accountId,
        enabled: account.enabled,
        configured,
        running: state?.bridge.connected ?? false,
        connected: state?.bridge.connected ?? false,
      };
    },

    isConfigured(account: ResolvedGarminAccount): boolean {
      // Garmin Messenger needs a binary and saved session — we can't check the
      // session from here, so just verify the binary is locatable.
      try {
        resolveBinary(account.config.binaryPath);
        return true;
      } catch {
        return false;
      }
    },
  },

  gateway: {
    async startAccount(ctx: ChannelGatewayContext<ResolvedGarminAccount>): Promise<void> {
      debugLog(`startAccount called for ${ctx.accountId}`);
      try {
        await startAccountInner(ctx);
        debugLog(`startAccount OK for ${ctx.accountId}`);
      } catch (err) {
        debugLog(`startAccount FAILED for ${ctx.accountId}: ${err}\n${(err as Error).stack ?? ""}`);
        throw err;
      }
    },

    async stopAccount(ctx: ChannelGatewayContext<ResolvedGarminAccount>): Promise<void> {
      const state = accounts.get(ctx.accountId);
      if (!state) return;

      try {
        if (state.bridge.connected) {
          await state.bridge.stopListening();
          await state.bridge.disconnect();
        }
      } catch (err) {
        ctx.log?.warn(`Error stopping account ${ctx.accountId}: ${err}`);
      }
      accounts.delete(ctx.accountId);
      ctx.setStatus({ ...ctx.getStatus(), running: false, connected: false });
      ctx.log?.info(`Account ${ctx.accountId}: stopped`);
    },

    async loginWithOtpRequest(accountId: string, phone: string, deviceName?: string): Promise<OtpRequestResult> {
      const { bridge } = getAccount(accountId);
      const result = await bridge.requestOtp(phone, deviceName);
      if (result.isError) {
        return { ok: false, error: result.text };
      }
      const data = result.json as { request_id?: string; valid_until?: string; attempts_remaining?: number } | null;
      return {
        ok: true,
        requestId: data?.request_id,
        validUntil: data?.valid_until,
        attemptsRemaining: data?.attempts_remaining,
      };
    },

    async loginWithOtpConfirm(accountId: string, phone: string, requestId: string, otpCode: string): Promise<OtpConfirmResult> {
      const state = getAccount(accountId);
      const result = await state.bridge.confirmOtp(requestId, phone, otpCode);
      if (result.isError) {
        return { ok: false, error: result.text };
      }
      const data = result.json as { instance_id?: string; fcm?: string } | null;

      // Update account state with new instance ID
      state.instanceId = data?.instance_id;

      // Warn if FCM registration failed (push notifications won't work)
      if (data?.fcm && !data.fcm.includes("registered")) {
        let log: RuntimeLogger | undefined;
        try { log = getGarminRuntime().logging.getChildLogger({ channel: "garmin-messenger" }); } catch {}
        log?.warn(`FCM registration failed: ${data.fcm}`);
      }

      // Auto-start listening after successful login
      await performPostLoginSetup(state, accountId);

      return {
        ok: true,
        instanceId: data?.instance_id,
        fcmStatus: data?.fcm,
      };
    },
  },

  outbound: {
    deliveryMode: "gateway",
    textChunkLimit: 160,
    chunkerMode: "text",

    async sendText(ctx: ChannelOutboundContext): Promise<OutboundDeliveryResult> {
      const { bridge } = getAccount(ctx.accountId ?? DEFAULT_ACCOUNT_ID);
      const result = await bridge.sendMessage([ctx.to], ctx.text);
      if (result.isError) {
        throw new Error(result.text);
      }
      const data = result.json as { message_id?: string; conversation_id?: string } | null;
      return {
        channel: "garmin-messenger",
        messageId: data?.message_id ?? `msg-${Date.now()}`,
        chatId: data?.conversation_id,
      };
    },

    async sendMedia(ctx: ChannelOutboundContext): Promise<OutboundDeliveryResult> {
      const accountId = ctx.accountId ?? DEFAULT_ACCOUNT_ID;
      const { bridge } = getAccount(accountId);

      let filePath = ctx.mediaUrl ?? "";
      let tmpDir: string | undefined;

      // For http(s) URLs, download to temp file
      if (/^https?:\/\//i.test(filePath)) {
        const { writeFileSync, mkdtempSync } = await import("node:fs");
        const { join: joinPath } = await import("node:path");
        const { tmpdir } = await import("node:os");

        tmpDir = mkdtempSync(joinPath(tmpdir(), "garmin-media-"));
        const pathname = new URL(filePath).pathname;
        const ext = pathname.split(".").pop() ?? "bin";
        const tmpFile = joinPath(tmpDir, `media.${ext}`);

        try {
          const MAX_MEDIA_BYTES = 1024 * 1024; // 1 MB
          const resp = await fetch(filePath);
          if (!resp.ok) throw new Error(`Download failed: HTTP ${resp.status}`);
          const ct = resp.headers.get("content-type") ?? "";
          if (ct && !ct.startsWith("image/") && !ct.startsWith("audio/")) {
            throw new Error(`Unsupported media content-type: ${ct}`);
          }
          const contentLength = Number(resp.headers.get("content-length"));
          if (contentLength > MAX_MEDIA_BYTES) {
            throw new Error(`Media too large: ${contentLength} bytes (max ${MAX_MEDIA_BYTES})`);
          }
          const buf = Buffer.from(await resp.arrayBuffer());
          if (buf.byteLength > MAX_MEDIA_BYTES) {
            throw new Error(`Media too large: ${buf.byteLength} bytes (max ${MAX_MEDIA_BYTES})`);
          }
          writeFileSync(tmpFile, buf);
          filePath = tmpFile;
        } catch (err) {
          throw new Error(`Failed to download media: ${err}`);
        }
      }

      try {
        const result = await bridge.sendMediaMessage([ctx.to], ctx.text, filePath);
        if (result.isError) {
          throw new Error(result.text);
        }
        const data = result.json as { message_id?: string; conversation_id?: string } | null;
        return {
          channel: "garmin-messenger",
          messageId: data?.message_id ?? `msg-${Date.now()}`,
          chatId: data?.conversation_id,
        };
      } finally {
        if (tmpDir) {
          const { rmSync } = await import("node:fs");
          rmSync(tmpDir, { recursive: true, force: true });
        }
      }
    },
  },

  security: {
    resolveDmPolicy(ctx) {
      const policy = ctx.account.config.dmPolicy ?? "allowlist";
      return {
        policy,
        allowFrom: ctx.account.config.allowFrom ?? [],
        policyPath: "channels.garmin-messenger.dmPolicy",
        allowFromPath: "channels.garmin-messenger.allowFrom",
        approveHint: "Use 'openclaw pairing approve garmin-messenger <phone>' to approve",
      };
    },

    collectWarnings(ctx) {
      const warnings: string[] = [];
      if (ctx.account.config.dmPolicy === "open") {
        warnings.push("DM policy is 'open' — anyone can message your bot");
      }
      return warnings;
    },
  },

  status: {
    defaultRuntime: {
      accountId: DEFAULT_ACCOUNT_ID,
      running: false,
      connected: false,
    },

    async probeAccount({ account }: { account: ResolvedGarminAccount; timeoutMs: number; cfg: OpenClawConfig }): Promise<{ healthy: boolean; loggedIn: boolean; listening: boolean; instanceId?: string; error?: string }> {
      const state = accounts.get(account.accountId);
      if (!state || !state.bridge.connected) {
        return { healthy: false, loggedIn: false, listening: false, error: "not connected" };
      }

      try {
        const status = await state.bridge.getStatus();
        return {
          healthy: status.logged_in,
          loggedIn: status.logged_in,
          listening: status.listening,
          instanceId: status.instance_id,
        };
      } catch (err) {
        return { healthy: false, loggedIn: false, listening: false, error: String(err) };
      }
    },
  },

  directory: {
    async listPeers({ accountId }: { cfg: OpenClawConfig; accountId?: string | null }): Promise<DirectoryPeer[]> {
      const state = accounts.get(accountId ?? DEFAULT_ACCOUNT_ID);
      if (!state || !state.bridge.connected) return [];

      try {
        const contacts = await state.bridge.readResourceJson<GarminContacts>("garmin://contacts");
        const peers: DirectoryPeer[] = [];
        for (const [id, member] of Object.entries(contacts.members ?? {})) {
          const phone = contacts.addresses?.[id];
          peers.push({
            kind: "user",
            id,
            name: member.displayName,
            handle: phone,
          });
        }
        return peers;
      } catch {
        return [];
      }
    },
  },

  pairing: {
    idLabel: "phone number",
    normalizeAllowEntry(entry: string): string {
      return entry.replace(/[^+\d]/g, "");
    },
  },

  setup: {
    validateInput: ({ input }) => {
      try {
        resolveBinary(input.cliPath ?? undefined);
        return null;
      } catch (err) {
        return `garmin-messenger binary not found. Either pass --cli-path or add it to PATH.\n${(err as Error).message}`;
      }
    },
    applyAccountConfig: ({ cfg, input }) => ({
      ...cfg,
      channels: {
        ...cfg.channels,
        "garmin-messenger": {
          ...cfg.channels?.["garmin-messenger"],
          enabled: true,
          ...(input.authDir ? { sessionDir: input.authDir } : {}),
          ...(input.cliPath ? { binaryPath: input.cliPath } : {}),
          ...(input.name ? { name: input.name } : {}),
        },
      },
    }),
  },

  auth: {
    async login({ cfg, runtime }) {
      const rl = createInterface({ input: process.stdin, output: process.stdout });
      const ask = (q: string) => new Promise<string>((resolve) => rl.question(q, resolve));
      try {
        const channelCfg = cfg.channels?.["garmin-messenger"] ?? {};
        const sessionDir = channelCfg.sessionDir ?? defaultSessionDir();
        const binaryPath = resolveBinary(channelCfg.binaryPath);

        const bridge = new MCPBridge({
          binaryPath,
          sessionDir,
          logger: { info() {}, warn() {}, error() {} },
        });
        await bridge.connect();
        try {
          const phone = (await ask("Phone number (e.g. +1234567890): ")).trim();
          if (!/^\+\d{7,15}$/.test(phone)) {
            runtime.error("Invalid phone number format. Use E.164 format (e.g. +1234567890).");
            return;
          }

          const otpResult = await bridge.requestOtp(phone);
          if (otpResult.isError) {
            runtime.error(`OTP request failed: ${otpResult.text}`);
            return;
          }
          const data = otpResult.json as { request_id?: string } | null;
          runtime.log("Verification code sent. Check your phone for SMS.");

          const otpCode = (await ask("Enter verification code: ")).trim();
          const confirmResult = await bridge.confirmOtp(data?.request_id ?? "", phone, otpCode);
          if (confirmResult.isError) {
            runtime.error(`Verification failed: ${confirmResult.text}`);
            return;
          }
          // Warn if FCM registration failed (push notifications won't work)
          const confirmData = confirmResult.json as { fcm?: string } | null;
          if (confirmData?.fcm && !confirmData.fcm.includes("registered")) {
            runtime.error(`FCM warning: ${confirmData.fcm}`);
          }
          runtime.log("Successfully logged in to Garmin Messenger!");
        } finally {
          await bridge.disconnect();
        }
      } finally {
        rl.close();
      }
    },
  },

  onboarding: garminOnboardingAdapter,

  agentTools: createGarminAgentTools,

  agentPrompt: {
    messageToolHints: (_params: { cfg: OpenClawConfig; accountId?: string | null }) => [
      "",
      "### Garmin Messenger (satellite channel)",
      "This channel sends messages via Garmin inReach satellite devices.",
      "Messages may be relayed over Iridium satellite — each message costs real money.",
      "",
      "**Login instructions (if account is not logged in):**",
      "If the Garmin Messenger account is not logged in, use the garmin_login tool:",
      "1. Call with action 'status' to check current login state",
      "2. Ask the user which phone number to use for Garmin login — do NOT assume their primary number",
      "3. Call with action 'request_otp' with the phone number the user provided",
      "4. Ask the user for the OTP code they received via SMS on that number",
      "5. Call with action 'confirm_otp' with the OTP code and request_id to complete login",
      "",
      "**Strict rules for this channel:**",
      "- Be EXTREMELY concise. Every character counts.",
      "- Aim for 1-3 short sentences max. Omit pleasantries, filler, and sign-offs.",
      "- No markdown formatting (bold, italic, headers) — plain text only.",
      "- No bullet lists or numbered lists — use compact prose instead.",
      "- No code blocks, tables, or structured formatting.",
      "- No emojis unless the user uses them first.",
      "- Strip all unnecessary whitespace and blank lines.",
      "- If a yes/no suffices, reply with just that.",
      "- Abbreviate where clear (e.g., 'info' not 'information', 'msg' not 'message').",
      "- Recipients may be on low-bandwidth satellite devices with tiny screens.",
      "",
      "**Good example:** 'Storm moving E, expect rain by 3pm. Stay on ridge trail.'",
      "**Bad example:** 'Hello! I wanted to let you know that there is a storm system currently moving in an easterly direction...'",
    ],
  },
};

function resolveMediaInboundDir(): string {
  const stateDir = process.env.OPENCLAW_STATE_DIR || join(homedir(), ".openclaw");
  return join(stateDir, "media", "inbound");
}

function garminMediaToMime(mediaType: string): { mime: string; ext: string } | null {
  switch (mediaType) {
    case "ImageAvif": return { mime: "image/avif", ext: ".avif" };
    case "AudioOgg": return { mime: "audio/ogg", ext: ".ogg" };
    default: return null;
  }
}

// Process a single inbound message (shared by embedded-meta and resource-fetch paths)
async function processMessage(
  state: AccountState,
  accountId: string,
  conversationId: string,
  msg: GarminMessage,
  runtime: ReturnType<typeof getGarminRuntime>,
  log: RuntimeLogger,
): Promise<void> {
  debugLog(`[inbound] processing msg=${msg.messageId} from=${msg.from ?? "?"} body=${JSON.stringify(msg.messageBody ?? "").slice(0, 80)} mediaId=${msg.mediaId ?? "(none)"}`);

  // Skip self-messages
  if (state.instanceId && msg.from === state.instanceId) {
    debugLog(`[inbound] SKIP self-message from=${msg.from}`);
    return;
  }

  // Track known senders for pairing
  if (msg.from) state.knownSenders.add(msg.from);

  const hasText = !!msg.messageBody;
  const hasMedia = !!msg.mediaId;

  // Skip messages with neither text nor media
  if (!hasText && !hasMedia) {
    debugLog(`[inbound] SKIP msg=${msg.messageId} — no text and no media`);
    return;
  }

  let mediaPath: string | undefined;
  let mimeType: string | undefined;

  if (hasMedia) {
    const resolved = garminMediaToMime(msg.mediaType ?? "");
    if (!resolved) {
      debugLog(`[inbound] SKIP unsupported media type: ${msg.mediaType}`);
      log.warn(`Skipping unsupported media type: ${msg.mediaType}`);
    } else {
      const { mime, ext } = resolved;
      const mediaDir = resolveMediaInboundDir();
      const outputPath = join(mediaDir, `${msg.mediaId}${ext}`);
      debugLog(`[inbound] downloading media: type=${msg.mediaType} → ${outputPath}`);
      try {
        await mkdir(mediaDir, { recursive: true });
        await state.bridge.downloadMedia(conversationId, msg.messageId, outputPath);
        mediaPath = outputPath;
        mimeType = mime;
        debugLog(`[inbound] media downloaded OK: ${outputPath}`);
      } catch (err) {
        debugLog(`[inbound] media download FAILED: ${err}`);
        log.warn(`Failed to download media ${msg.mediaId}: ${err}`);
      }
    }
  }

  // Resolve body text
  let bodyText: string;
  if (hasText) {
    bodyText = msg.messageBody!;
  } else if (msg.transcription) {
    bodyText = msg.transcription;
  } else {
    bodyText = "[media]";
  }

  const sender = msg.from ?? "unknown";
  debugLog(`[inbound] dispatching: sender=${sender} body=${JSON.stringify(bodyText).slice(0, 80)} media=${mediaPath ?? "(none)"}`);

  // Build metadata from rich message fields
  const metadata: Record<string, unknown> = {};
  if (msg.userLocation) metadata.userLocation = msg.userLocation;
  if (msg.referencePoint) metadata.referencePoint = msg.referencePoint;
  if (msg.liveTrackUrl) metadata.liveTrackUrl = msg.liveTrackUrl;
  if (msg.mapShareUrl) metadata.mapShareUrl = msg.mapShareUrl;
  if (msg.mapSharePassword) metadata.mapSharePassword = msg.mapSharePassword;
  if (msg.fromDeviceType) metadata.fromDeviceType = msg.fromDeviceType;
  if (msg.mediaMetadata) metadata.mediaMetadata = msg.mediaMetadata;

  // Serialize metadata into body so the agent can see it
  const metaContext = serializeMessageContext(msg);
  if (metaContext) {
    bodyText += "\n" + metaContext;
  }

  try {
    const cfg = runtime.config.loadConfig();
    const ctx = runtime.channel.reply.finalizeInboundContext({
      Body: bodyText,
      From: `garmin-messenger:${sender}`,
      To: `garmin-messenger:${conversationId}`,
      SessionKey: `garmin-messenger:${accountId}:${sender}`,
      AccountId: accountId,
      Provider: "garmin-messenger",
      Surface: "garmin-messenger",
      ChatType: "direct" as const,
      MessageSid: msg.messageId,
      SenderName: sender,
      SenderId: sender,
      OriginatingChannel: "garmin-messenger",
      OriginatingTo: `garmin-messenger:${sender}`,
      CommandAuthorized: false,
      ...(mediaPath && { MediaPath: mediaPath, MediaUrl: mediaPath }),
      ...(mimeType && { MediaType: mimeType }),
      ...(Object.keys(metadata).length > 0 && { Metadata: metadata }),
    });
    debugLog(`[inbound] finalized inbound context OK`);

    await runtime.channel.reply.dispatchReplyWithBufferedBlockDispatcher({
      ctx,
      cfg,
      dispatcherOptions: {
        deliver: async (payload) => {
          debugLog(`[inbound] deliver callback: text=${JSON.stringify(payload.text ?? "").slice(0, 80)} mediaUrl=${payload.mediaUrl ?? "(none)"}`);
          if (payload.text) {
            await state.bridge.sendMessage([sender], payload.text);
            debugLog(`[inbound] reply text sent to ${sender}`);
          }
          if (payload.mediaUrl) {
            await state.bridge.sendMediaMessage([sender], payload.text ?? "", payload.mediaUrl);
            debugLog(`[inbound] reply media sent to ${sender}`);
          }
        },
        onError: (err, info) => {
          debugLog(`[inbound] dispatch onError: kind=${info.kind} err=${err}`);
          log.error(`Reply dispatch ${info.kind} failed: ${err}`);
        },
      },
    });
    debugLog(`[inbound] dispatch complete for msg=${msg.messageId}`);
  } catch (err) {
    debugLog(`[inbound] FAILED to process msg=${msg.messageId}: ${err}\n${(err as Error).stack ?? ""}`);
    log.error(`Failed to process inbound message ${msg.messageId}: ${err}`);
  }
}

// Handle resource update notifications from MCP server
async function handleResourceUpdate(accountId: string, uri: string, meta?: Record<string, unknown>): Promise<void> {
  debugLog(`[inbound] handleResourceUpdate(${accountId}, ${uri}, meta=${JSON.stringify(meta)})`);

  const state = accounts.get(accountId);
  if (!state) {
    debugLog(`[inbound] no account state for ${accountId}, ignoring`);
    return;
  }

  // Extract conversation ID from sentinel URI (garmin://messages with meta)
  // or from legacy templated URI (garmin://conversations/{id}/messages)
  let conversationId: string | undefined;
  if (uri === "garmin://messages") {
    conversationId = meta?.conversation_id as string | undefined;
  } else {
    const match = uri.match(/^garmin:\/\/conversations\/([^/]+)\/messages$/);
    if (match) conversationId = match[1];
  }

  if (!conversationId) {
    debugLog(`[inbound] could not extract conversation ID from URI=${uri}, ignoring`);
    return;
  }

  let runtime;
  try {
    runtime = getGarminRuntime();
  } catch (err) {
    debugLog(`[inbound] runtime not available: ${err}`);
    return;
  }
  const log = runtime.logging.getChildLogger({ channel: "garmin-messenger" });

  const eventType = meta?.type as string | undefined;

  // Status updates: log and ignore (for future use)
  if (eventType === "status_update") {
    debugLog(`[inbound] status update for conversation=${conversationId}, ignoring`);
    return;
  }

  // Embedded message: use directly without re-fetching
  if (eventType === "message") {
    const embedded = meta?.message as GarminMessage | undefined;
    if (embedded) {
      debugLog(`[inbound] using embedded message msg=${embedded.messageId}`);
      await processMessage(state, accountId, conversationId, embedded, runtime, log);
      debugLog(`[inbound] handleResourceUpdate done for ${conversationId}`);
      return;
    }
  }

  // Notifications without embedded messages are not actionable — messages
  // arrive via SignalR/FCM push with full payloads embedded in metadata.
  debugLog(`[inbound] notification without embedded message for conversation=${conversationId}, ignoring`);
}

function formatLocation(label: string, loc: GarminUserLocation): string {
  const parts: string[] = [];
  if (loc.latitudeDegrees != null && loc.longitudeDegrees != null) {
    parts.push(`${loc.latitudeDegrees}, ${loc.longitudeDegrees}`);
  }
  if (loc.elevationMeters != null) parts.push(`${loc.elevationMeters}m`);
  if (loc.groundVelocityMetersPerSecond != null) parts.push(`${loc.groundVelocityMetersPerSecond}m/s`);
  if (loc.courseDegrees != null) parts.push(`course ${loc.courseDegrees}\u00B0`);
  return parts.length > 0 ? `${label}: ${parts.join(", ")}` : "";
}

function serializeMessageContext(msg: GarminMessage): string {
  const lines: string[] = [];
  if (msg.userLocation) {
    const s = formatLocation("Location", msg.userLocation);
    if (s) lines.push(s);
  }
  if (msg.referencePoint) {
    const s = formatLocation("Reference Point", msg.referencePoint);
    if (s) lines.push(s);
  }
  if (msg.liveTrackUrl) lines.push(`Live Track: ${msg.liveTrackUrl}`);
  if (msg.mapShareUrl) lines.push(`Map Share: ${msg.mapShareUrl}`);
  if (msg.mapSharePassword) lines.push(`Map Password: ${msg.mapSharePassword}`);
  if (lines.length === 0) return "";
  return "---\nMessage metadata:\n" + lines.join("\n");
}
