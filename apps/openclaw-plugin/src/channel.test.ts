import { describe, it, expect, vi, beforeEach } from "vitest";

// Mock binary resolution before importing channel
const mockResolveBinary = vi.fn(() => "/mock/garmin-messenger");
vi.mock("./binary.ts", () => ({
  resolveBinary: (...args: any[]) => mockResolveBinary(...args),
  ensureBinary: async (...args: any[]) => mockResolveBinary(...args),
}));

// Mock runtime module
const mockDispatch = vi.fn(async (params: any) => {
  // Simulate calling deliver with a text payload
  return {};
});
const mockFinalizeInboundContext = vi.fn((ctx: any) => ctx);
const mockLoadConfig = vi.fn(() => ({}));
const mockGetChildLogger = vi.fn(() => ({
  debug: vi.fn(),
  info: vi.fn(),
  warn: vi.fn(),
  error: vi.fn(),
}));

const mockPluginRuntime = {
  config: { loadConfig: mockLoadConfig },
  channel: {
    reply: {
      dispatchReplyWithBufferedBlockDispatcher: mockDispatch,
      finalizeInboundContext: mockFinalizeInboundContext,
    },
  },
  logging: { getChildLogger: mockGetChildLogger },
};

vi.mock("./runtime.ts", () => ({
  getGarminRuntime: () => mockPluginRuntime,
  setGarminRuntime: vi.fn(),
  resetGarminRuntime: vi.fn(),
}));

// Mock MCPBridge
vi.mock("./mcp-bridge.ts", () => {
  return {
    MCPBridge: vi.fn().mockImplementation(function () { return {
      connected: false,
      connect: vi.fn(async function (this: { connected: boolean }) {
        this.connected = true;
      }),
      disconnect: vi.fn(async function (this: { connected: boolean }) {
        this.connected = false;
      }),
      getStatus: vi.fn(async () => ({
        logged_in: true,
        listening: false,
        instance_id: "test-instance",
      })),
      startListening: vi.fn(async () => ({ isError: false, text: '{"listening":true}', json: { listening: true } })),
      stopListening: vi.fn(async () => ({ isError: false, text: '{"listening":false}', json: { listening: false } })),
      sendMessage: vi.fn(async () => ({
        isError: false,
        text: '{"message_id":"msg-1","conversation_id":"conv-1"}',
        json: { message_id: "msg-1", conversation_id: "conv-1" },
      })),
      sendMediaMessage: vi.fn(async () => ({
        isError: false,
        text: '{"message_id":"msg-2","conversation_id":"conv-1"}',
        json: { message_id: "msg-2", conversation_id: "conv-1" },
      })),
      requestOtp: vi.fn(async () => ({
        isError: false,
        text: '{"request_id":"req-123","valid_until":"2026-02-08T12:00:00Z","attempts_remaining":3}',
        json: { request_id: "req-123", valid_until: "2026-02-08T12:00:00Z", attempts_remaining: 3 },
      })),
      confirmOtp: vi.fn(async () => ({
        isError: false,
        text: '{"success":true,"instance_id":"new-instance","fcm":"FCM push notifications registered"}',
        json: { success: true, instance_id: "new-instance", fcm: "FCM push notifications registered" },
      })),
      downloadMedia: vi.fn(async () => ({
        filePath: "/tmp/media/test.avif",
        bytes: 1234,
        mediaType: "ImageAvif",
      })),
      readResourceJson: vi.fn(async () => ({
        members: { "user-1": { displayName: "Alice" } },
        conversations: [],
        addresses: { "user-1": "+15555550100" },
      })),
      subscribe: vi.fn(async () => {}),
    }; }),
  };
});

import { garminPlugin, _resetForTesting } from "./channel.ts";
import { MCPBridge } from "./mcp-bridge.ts";
import type {
  ChannelGatewayContext,
  ChannelOutboundContext,
  ChannelSecurityContext,
  ChannelAccountSnapshot,
  ResolvedGarminAccount,
  OpenClawConfig,
} from "./types.ts";
import { DEFAULT_ACCOUNT_ID } from "./types.ts";

// ---------------------------------------------------------------------------
// Helpers — build context objects for adapter calls
// ---------------------------------------------------------------------------

const mockLog = {
  debug: vi.fn(),
  info: vi.fn(),
  warn: vi.fn(),
  error: vi.fn(),
};

function makeAccount(overrides: Partial<ResolvedGarminAccount> = {}): ResolvedGarminAccount {
  return {
    accountId: DEFAULT_ACCOUNT_ID,
    enabled: true,
    config: {},
    ...overrides,
  };
}

function makeGatewayCtx(overrides: Partial<ChannelGatewayContext> = {}): ChannelGatewayContext {
  const controller = new AbortController();
  let status: ChannelAccountSnapshot = { accountId: DEFAULT_ACCOUNT_ID };
  return {
    cfg: {},
    accountId: DEFAULT_ACCOUNT_ID,
    account: makeAccount(),
    runtime: { log: console.log, error: console.error, exit: process.exit },
    abortSignal: controller.signal,
    log: mockLog,
    getStatus: () => status,
    setStatus: (next) => { status = next; },
    ...overrides,
  };
}

function makeOutboundCtx(overrides: Partial<ChannelOutboundContext> = {}): ChannelOutboundContext {
  return {
    cfg: {},
    to: "+15555550100",
    text: "Hello!",
    accountId: DEFAULT_ACCOUNT_ID,
    ...overrides,
  };
}

function makeSecurityCtx(overrides: Partial<ChannelSecurityContext> = {}): ChannelSecurityContext {
  return {
    cfg: {},
    accountId: DEFAULT_ACCOUNT_ID,
    account: makeAccount(),
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("garminPlugin", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    _resetForTesting();
  });

  it("has correct id", () => {
    expect(garminPlugin.id).toBe("garmin-messenger");
  });

  it("has required meta fields", () => {
    expect(garminPlugin.meta.id).toBe("garmin-messenger");
    expect(garminPlugin.meta.label).toBe("Garmin Messenger");
    expect(garminPlugin.meta.selectionLabel).toBe("Garmin Messenger");
    expect(garminPlugin.meta.docsPath).toBe("/channels/garmin-messenger");
    expect(garminPlugin.meta.blurb).toBeTruthy();
  });

  it("has capabilities", () => {
    expect(garminPlugin.capabilities.chatTypes).toEqual(["direct"]);
    expect(garminPlugin.capabilities.media).toBe(true);
    expect(garminPlugin.capabilities.reactions).toBe(false);
  });

  describe("config adapter", () => {
    it("listAccountIds returns empty when not enabled", () => {
      const ids = garminPlugin.config.listAccountIds({});
      expect(ids).toEqual([]);
    });

    it("listAccountIds returns default when enabled", () => {
      const ids = garminPlugin.config.listAccountIds({
        channels: { "garmin-messenger": { enabled: true } },
      });
      expect(ids).toEqual([DEFAULT_ACCOUNT_ID]);
    });

    it("resolveAccount returns resolved account", () => {
      const account = garminPlugin.config.resolveAccount(
        { channels: { "garmin-messenger": { enabled: true, dmPolicy: "open" } } },
        "default",
      );
      expect(account.accountId).toBe("default");
      expect(account.enabled).toBe(true);
      expect(account.config.dmPolicy).toBe("open");
    });

    it("isConfigured returns true when binary is locatable", () => {
      const account = makeAccount();
      expect(garminPlugin.config.isConfigured!(account, {})).toBe(true);
    });

    it("describeAccount returns snapshot for unstarted account", () => {
      const account = makeAccount();
      const snapshot = garminPlugin.config.describeAccount!(account, {});
      expect(snapshot.accountId).toBe(DEFAULT_ACCOUNT_ID);
      expect(snapshot.enabled).toBe(true);
      expect(snapshot.configured).toBe(true);
      expect(snapshot.running).toBe(false);
      expect(snapshot.connected).toBe(false);
    });
  });

  describe("agentPrompt.messageToolHints", () => {
    it("returns satellite messaging hints", () => {
      const hints = garminPlugin.agentPrompt!.messageToolHints!({ cfg: {} });
      expect(hints.length).toBeGreaterThan(5);
      expect(hints.some((h) => /satellite/i.test(h))).toBe(true);
      expect(hints.some((h) => /concise/i.test(h))).toBe(true);
      expect(hints.some((h) => /plain text/i.test(h))).toBe(true);
    });
  });

  describe("security.resolveDmPolicy", () => {
    it("returns open policy when configured", () => {
      const result = garminPlugin.security!.resolveDmPolicy!(
        makeSecurityCtx({ account: makeAccount({ config: { dmPolicy: "open" } }) }),
      );
      expect(result).not.toBeNull();
      expect(result!.policy).toBe("open");
      expect(result!.allowFrom).toEqual([]);
      expect(result!.policyPath).toBe("channels.garmin-messenger.dmPolicy");
      expect(result!.allowFromPath).toBe("channels.garmin-messenger.allowFrom");
      expect(typeof result!.approveHint).toBe("string");
      expect(result!.approveHint.length).toBeGreaterThan(0);
    });

    it("returns allowlist policy with phone numbers", () => {
      const result = garminPlugin.security!.resolveDmPolicy!(
        makeSecurityCtx({
          account: makeAccount({ config: { dmPolicy: "allowlist", allowFrom: ["+15555550100"] } }),
        }),
      );
      expect(result!.policy).toBe("allowlist");
      expect(result!.allowFrom).toEqual(["+15555550100"]);
    });

    it("defaults to allowlist policy", () => {
      const result = garminPlugin.security!.resolveDmPolicy!(makeSecurityCtx());
      expect(result!.policy).toBe("allowlist");
    });
  });

  describe("security.collectWarnings", () => {
    it("warns on open policy", () => {
      const warnings = garminPlugin.security!.collectWarnings!(
        makeSecurityCtx({ account: makeAccount({ config: { dmPolicy: "open" } }) }),
      ) as string[];
      expect(warnings.length).toBe(1);
      expect(warnings[0]).toContain("open");
    });

    it("no warnings for pairing", () => {
      const warnings = garminPlugin.security!.collectWarnings!(makeSecurityCtx()) as string[];
      expect(warnings).toEqual([]);
    });
  });

  describe("status.probeAccount", () => {
    it("returns not connected for unknown account", async () => {
      const result = await garminPlugin.status!.probeAccount!({
        account: makeAccount(),
        timeoutMs: 5000,
        cfg: {},
      });
      expect((result as any).healthy).toBe(false);
      expect((result as any).error).toBe("not connected");
    });
  });

  describe("gateway", () => {
    it("starts and stops an account", async () => {
      const ctx = makeGatewayCtx();
      await garminPlugin.gateway!.startAccount!(ctx);

      // After starting, status should work
      const probeResult = await garminPlugin.status!.probeAccount!({
        account: makeAccount(),
        timeoutMs: 5000,
        cfg: {},
      });
      expect((probeResult as any).loggedIn).toBe(true);
      expect((probeResult as any).instanceId).toBe("test-instance");

      await garminPlugin.gateway!.stopAccount!(ctx);
    });
  });

  describe("outbound", () => {
    it("sends a text message", async () => {
      const ctx = makeGatewayCtx();
      await garminPlugin.gateway!.startAccount!(ctx);

      const result = await garminPlugin.outbound!.sendText!(makeOutboundCtx());
      expect(result.channel).toBe("garmin-messenger");
      expect(result.messageId).toBe("msg-1");
      expect(result.chatId).toBe("conv-1");

      await garminPlugin.gateway!.stopAccount!(ctx);
    });

    it("sends a media message", async () => {
      const ctx = makeGatewayCtx();
      await garminPlugin.gateway!.startAccount!(ctx);

      const result = await garminPlugin.outbound!.sendMedia!(
        makeOutboundCtx({ text: "Photo", mediaUrl: "/tmp/photo.jpg" }),
      );
      expect(result.channel).toBe("garmin-messenger");
      expect(result.messageId).toBe("msg-2");

      await garminPlugin.gateway!.stopAccount!(ctx);
    });

    it("throws for unknown account", async () => {
      await expect(
        garminPlugin.outbound!.sendText!(makeOutboundCtx({ accountId: "unknown" })),
      ).rejects.toThrow("Account unknown not started");
    });
  });

  describe("directory", () => {
    it("lists peers from contacts", async () => {
      const ctx = makeGatewayCtx();
      await garminPlugin.gateway!.startAccount!(ctx);

      const peers = await garminPlugin.directory!.listPeers!({ cfg: {}, accountId: DEFAULT_ACCOUNT_ID, runtime: { log: console.log, error: console.error, exit: process.exit } });
      expect(peers).toHaveLength(1);
      expect(peers[0].kind).toBe("user");
      expect(peers[0].id).toBe("user-1");
      expect(peers[0].name).toBe("Alice");
      expect(peers[0].handle).toBe("+15555550100");

      await garminPlugin.gateway!.stopAccount!(ctx);
    });

    it("returns empty for unknown account", async () => {
      const peers = await garminPlugin.directory!.listPeers!({ cfg: {}, accountId: "unknown", runtime: { log: console.log, error: console.error, exit: process.exit } });
      expect(peers).toEqual([]);
    });

    it("defaults accountId when not provided", async () => {
      const ctx = makeGatewayCtx();
      await garminPlugin.gateway!.startAccount!(ctx);

      const peers = await garminPlugin.directory!.listPeers!({ cfg: {}, runtime: { log: console.log, error: console.error, exit: process.exit } });
      expect(peers).toHaveLength(1);

      await garminPlugin.gateway!.stopAccount!(ctx);
    });
  });

  describe("pairing", () => {
    it("has idLabel set to phone number", () => {
      expect(garminPlugin.pairing).toBeDefined();
      expect(garminPlugin.pairing!.idLabel).toBe("phone number");
    });

    it("normalizeAllowEntry strips non-phone characters", () => {
      const normalize = garminPlugin.pairing!.normalizeAllowEntry!;
      expect(normalize("+1 (555) 555-0100")).toBe("+15555550100");
      expect(normalize("  +44 7911 123456  ")).toBe("+447911123456");
    });
  });

  describe("inbound messages", () => {
    // Helper to capture the onResourceUpdated callback and bridge mock from startAccount
    async function startAndCapture() {
      const MockBridge = vi.mocked(MCPBridge);
      let capturedCallback: ((uri: string, meta?: Record<string, unknown>) => void) | undefined;
      let bridgeInstance: any;

      MockBridge.mockImplementationOnce(function (opts: any) {
        capturedCallback = opts.onResourceUpdated;
        bridgeInstance = {
          connected: false,
          connect: vi.fn(async function (this: { connected: boolean }) { this.connected = true; }),
          disconnect: vi.fn(async function (this: { connected: boolean }) { this.connected = false; }),
          getStatus: vi.fn(async () => ({ logged_in: true, listening: false, instance_id: "test-instance" })),
          startListening: vi.fn(async () => ({ isError: false, text: "{}", json: {} })),
          stopListening: vi.fn(async () => ({ isError: false, text: "{}", json: {} })),
          sendMessage: vi.fn(async () => ({ isError: false, text: "{}", json: {} })),
          sendMediaMessage: vi.fn(async () => ({ isError: false, text: "{}", json: {} })),
          downloadMedia: vi.fn(async () => ({ filePath: "/mock/media/img.avif", bytes: 1234, mediaType: "ImageAvif" })),
          readResourceJson: vi.fn(async () => ({ metaData: {}, messages: [], limit: 50 })),
          subscribe: vi.fn(async () => {}),
        };
        return bridgeInstance;
      });

      await garminPlugin.gateway!.startAccount!(makeGatewayCtx());
      return { callback: capturedCallback!, bridge: bridgeInstance };
    }

    it("processes text-only inbound message", async () => {
      const { callback, bridge } = await startAndCapture();

      await callback("garmin://messages", {
        type: "message",
        conversation_id: "conv-1",
        message: { messageId: "msg-100", messageBody: "Hello from satellite", from: "sender-1" },
      });
      await new Promise((r) => setTimeout(r, 10));

      expect(mockDispatch).toHaveBeenCalledWith(
        expect.objectContaining({
          ctx: expect.objectContaining({
            Body: "Hello from satellite",
            From: "garmin-messenger:sender-1",
            MessageSid: "msg-100",
            Provider: "garmin-messenger",
            Surface: "garmin-messenger",
            SenderId: "sender-1",
            CommandAuthorized: false,
          }),
          cfg: expect.any(Object),
          dispatcherOptions: expect.objectContaining({
            deliver: expect.any(Function),
            onError: expect.any(Function),
          }),
        }),
      );
      // No media download for text-only
      expect(bridge.downloadMedia).not.toHaveBeenCalled();
      // No resource fetch for embedded messages
      expect(bridge.readResourceJson).not.toHaveBeenCalled();

      await garminPlugin.gateway!.stopAccount!(makeGatewayCtx());
    });

    it("processes media-only inbound message (image)", async () => {
      const { callback, bridge } = await startAndCapture();

      await callback("garmin://messages", {
        type: "message",
        conversation_id: "conv-1",
        message: { messageId: "msg-200", from: "sender-1", mediaId: "media-abc", mediaType: "ImageAvif" },
      });
      await new Promise((r) => setTimeout(r, 10));

      expect(bridge.downloadMedia).toHaveBeenCalledWith("conv-1", "msg-200", expect.stringContaining("media-abc.avif"));
      expect(mockDispatch).toHaveBeenCalledWith(
        expect.objectContaining({
          ctx: expect.objectContaining({
            Body: "[media]",
            From: "garmin-messenger:sender-1",
            MediaPath: expect.stringContaining("media-abc.avif"),
            MediaUrl: expect.stringContaining("media-abc.avif"),
            MediaType: "image/avif",
          }),
        }),
      );

      await garminPlugin.gateway!.stopAccount!(makeGatewayCtx());
    });

    it("processes text + media inbound message", async () => {
      const { callback, bridge } = await startAndCapture();

      await callback("garmin://messages", {
        type: "message",
        conversation_id: "conv-1",
        message: { messageId: "msg-300", messageBody: "Check this photo", from: "sender-1", mediaId: "media-xyz", mediaType: "ImageAvif" },
      });
      await new Promise((r) => setTimeout(r, 10));

      expect(bridge.downloadMedia).toHaveBeenCalled();
      expect(mockDispatch).toHaveBeenCalledWith(
        expect.objectContaining({
          ctx: expect.objectContaining({
            Body: "Check this photo",
            MediaPath: expect.stringContaining("media-xyz.avif"),
            MediaType: "image/avif",
          }),
        }),
      );

      await garminPlugin.gateway!.stopAccount!(makeGatewayCtx());
    });

    it("uses transcription as body for audio without messageBody", async () => {
      const { callback, bridge } = await startAndCapture();

      await callback("garmin://messages", {
        type: "message",
        conversation_id: "conv-1",
        message: { messageId: "msg-400", from: "sender-1", mediaId: "audio-1", mediaType: "AudioOgg", transcription: "This is a voice note" },
      });
      await new Promise((r) => setTimeout(r, 10));

      expect(mockDispatch).toHaveBeenCalledWith(
        expect.objectContaining({
          ctx: expect.objectContaining({
            Body: "This is a voice note",
            MediaType: "audio/ogg",
          }),
        }),
      );

      await garminPlugin.gateway!.stopAccount!(makeGatewayCtx());
    });

    it("handles media download failure gracefully", async () => {
      const { callback, bridge } = await startAndCapture();

      bridge.downloadMedia.mockRejectedValueOnce(new Error("download failed"));

      await callback("garmin://messages", {
        type: "message",
        conversation_id: "conv-1",
        message: { messageId: "msg-500", messageBody: "Photo attached", from: "sender-1", mediaId: "media-fail", mediaType: "ImageAvif" },
      });
      await new Promise((r) => setTimeout(r, 10));

      // Should still dispatch the text body without media
      expect(mockDispatch).toHaveBeenCalledWith(
        expect.objectContaining({
          ctx: expect.objectContaining({
            Body: "Photo attached",
            From: "garmin-messenger:sender-1",
          }),
        }),
      );
      // Should NOT have MediaPath set
      const call = mockDispatch.mock.calls[0][0];
      expect(call.ctx.MediaPath).toBeUndefined();

      await garminPlugin.gateway!.stopAccount!(makeGatewayCtx());
    });

    it("filters out self-messages", async () => {
      const { callback, bridge } = await startAndCapture();

      // Self-message should be ignored
      await callback("garmin://messages", {
        type: "message",
        conversation_id: "conv-1",
        message: { messageId: "msg-600", messageBody: "My own message", from: "test-instance" },
      });
      await new Promise((r) => setTimeout(r, 10));
      expect(mockDispatch).not.toHaveBeenCalled();

      // Other sender's message should be dispatched
      await callback("garmin://messages", {
        type: "message",
        conversation_id: "conv-1",
        message: { messageId: "msg-601", messageBody: "Their reply", from: "sender-1" },
      });
      await new Promise((r) => setTimeout(r, 10));

      expect(mockDispatch).toHaveBeenCalledTimes(1);
      expect(mockDispatch).toHaveBeenCalledWith(
        expect.objectContaining({
          ctx: expect.objectContaining({
            Body: "Their reply",
            From: "garmin-messenger:sender-1",
          }),
        }),
      );

      await garminPlugin.gateway!.stopAccount!(makeGatewayCtx());
    });

    it("deliver callback sends text via bridge", async () => {
      const { callback, bridge } = await startAndCapture();

      // Make dispatch call deliver with a text payload
      mockDispatch.mockImplementationOnce(async (params: any) => {
        await params.dispatcherOptions.deliver({ text: "Agent reply" }, { kind: "final" });
        return {};
      });

      await callback("garmin://messages", {
        type: "message",
        conversation_id: "conv-1",
        message: { messageId: "msg-700", messageBody: "Hello", from: "sender-1" },
      });
      await new Promise((r) => setTimeout(r, 10));

      expect(bridge.sendMessage).toHaveBeenCalledWith(["sender-1"], "Agent reply");

      await garminPlugin.gateway!.stopAccount!(makeGatewayCtx());
    });

    it("deliver callback sends media via bridge", async () => {
      const { callback, bridge } = await startAndCapture();

      mockDispatch.mockImplementationOnce(async (params: any) => {
        await params.dispatcherOptions.deliver({ mediaUrl: "/tmp/reply.jpg" }, { kind: "final" });
        return {};
      });

      await callback("garmin://messages", {
        type: "message",
        conversation_id: "conv-1",
        message: { messageId: "msg-800", messageBody: "Send photo", from: "sender-1" },
      });
      await new Promise((r) => setTimeout(r, 10));

      expect(bridge.sendMediaMessage).toHaveBeenCalledWith(["sender-1"], "", "/tmp/reply.jpg");

      await garminPlugin.gateway!.stopAccount!(makeGatewayCtx());
    });

    it("appends metadata context to Body when rich fields present", async () => {
      const { callback } = await startAndCapture();

      await callback("garmin://messages", {
        type: "message",
        conversation_id: "conv-1",
        message: {
          messageId: "msg-meta-1",
          messageBody: "I'm at camp",
          from: "sender-1",
          userLocation: { latitudeDegrees: 45.123, longitudeDegrees: -110.456, elevationMeters: 2500 },
          liveTrackUrl: "https://share.garmin.com/track123",
          fromDeviceType: "inReach",
        },
      });
      await new Promise((r) => setTimeout(r, 10));

      expect(mockDispatch).toHaveBeenCalledTimes(1);
      const ctx = mockDispatch.mock.calls[0][0].ctx;
      expect(ctx.Body).toContain("I'm at camp");
      expect(ctx.Body).toContain("---\nMessage metadata:\n");
      expect(ctx.Body).toContain("Location: 45.123, -110.456, 2500m");
      expect(ctx.Body).toContain("Live Track: https://share.garmin.com/track123");
      expect(ctx.Body).not.toContain("Device:");
      expect(ctx.Metadata).toEqual({
        userLocation: { latitudeDegrees: 45.123, longitudeDegrees: -110.456, elevationMeters: 2500 },
        liveTrackUrl: "https://share.garmin.com/track123",
        fromDeviceType: "inReach",
      });

      await garminPlugin.gateway!.stopAccount!(makeGatewayCtx());
    });

    it("includes velocity and course in location when present", async () => {
      const { callback } = await startAndCapture();

      await callback("garmin://messages", {
        type: "message",
        conversation_id: "conv-1",
        message: {
          messageId: "msg-meta-2",
          messageBody: "Moving",
          from: "sender-1",
          userLocation: {
            latitudeDegrees: 50.0,
            longitudeDegrees: 14.0,
            elevationMeters: 300,
            groundVelocityMetersPerSecond: 1.5,
            courseDegrees: 270,
          },
        },
      });
      await new Promise((r) => setTimeout(r, 10));

      const ctx = mockDispatch.mock.calls[0][0].ctx;
      expect(ctx.Body).toContain("Message metadata:");
      expect(ctx.Body).toContain("Location: 50, 14, 300m, 1.5m/s, course 270°");

      await garminPlugin.gateway!.stopAccount!(makeGatewayCtx());
    });

    it("serializes referencePoint separately from userLocation", async () => {
      const { callback } = await startAndCapture();

      await callback("garmin://messages", {
        type: "message",
        conversation_id: "conv-1",
        message: {
          messageId: "msg-meta-3",
          messageBody: "Check this spot",
          from: "sender-1",
          referencePoint: { latitudeDegrees: 48.8566, longitudeDegrees: 2.3522 },
        },
      });
      await new Promise((r) => setTimeout(r, 10));

      const ctx = mockDispatch.mock.calls[0][0].ctx;
      expect(ctx.Body).toContain("Message metadata:");
      expect(ctx.Body).toContain("Reference Point: 48.8566, 2.3522");

      await garminPlugin.gateway!.stopAccount!(makeGatewayCtx());
    });

    it("serializes mapShareUrl and mapSharePassword", async () => {
      const { callback } = await startAndCapture();

      await callback("garmin://messages", {
        type: "message",
        conversation_id: "conv-1",
        message: {
          messageId: "msg-meta-4",
          messageBody: "Here's my map",
          from: "sender-1",
          mapShareUrl: "https://share.garmin.com/map456",
          mapSharePassword: "secret123",
        },
      });
      await new Promise((r) => setTimeout(r, 10));

      const ctx = mockDispatch.mock.calls[0][0].ctx;
      expect(ctx.Body).toContain("Message metadata:");
      expect(ctx.Body).toContain("Map Share: https://share.garmin.com/map456");
      expect(ctx.Body).toContain("Map Password: secret123");

      await garminPlugin.gateway!.stopAccount!(makeGatewayCtx());
    });

    it("does not append metadata context when no rich fields present", async () => {
      const { callback } = await startAndCapture();

      await callback("garmin://messages", {
        type: "message",
        conversation_id: "conv-1",
        message: { messageId: "msg-plain-1", messageBody: "Just text", from: "sender-1" },
      });
      await new Promise((r) => setTimeout(r, 10));

      expect(mockDispatch).toHaveBeenCalledTimes(1);
      const ctx = mockDispatch.mock.calls[0][0].ctx;
      expect(ctx.Body).toBe("Just text");
      expect(ctx.Body).not.toContain("Message metadata:");
      expect(ctx.Metadata).toBeUndefined();

      await garminPlugin.gateway!.stopAccount!(makeGatewayCtx());
    });

    it("skips download for unsupported media type", async () => {
      const { callback, bridge } = await startAndCapture();

      await callback("garmin://messages", {
        type: "message",
        conversation_id: "conv-1",
        message: { messageId: "msg-unsup", messageBody: "File attached", from: "sender-1", mediaId: "media-doc", mediaType: "DocumentPdf" },
      });
      await new Promise((r) => setTimeout(r, 10));

      // Should NOT attempt to download unsupported media type
      expect(bridge.downloadMedia).not.toHaveBeenCalled();
      // Should still dispatch the text body without media
      expect(mockDispatch).toHaveBeenCalledWith(
        expect.objectContaining({
          ctx: expect.objectContaining({
            Body: "File attached",
            From: "garmin-messenger:sender-1",
          }),
        }),
      );
      const call = mockDispatch.mock.calls[0][0];
      expect(call.ctx.MediaPath).toBeUndefined();
      expect(call.ctx.MediaType).toBeUndefined();

      await garminPlugin.gateway!.stopAccount!(makeGatewayCtx());
    });

    it("ignores status_update notifications gracefully", async () => {
      const { callback, bridge } = await startAndCapture();

      await callback("garmin://messages", {
        type: "status_update",
        conversation_id: "conv-1",
        status_update: { messageId: { conversationId: "conv-1", messageId: "msg-900" }, status: "Delivered" },
      });
      await new Promise((r) => setTimeout(r, 10));

      // Should not dispatch anything or fetch resources
      expect(mockDispatch).not.toHaveBeenCalled();
      expect(bridge.readResourceJson).not.toHaveBeenCalled();

      await garminPlugin.gateway!.stopAccount!(makeGatewayCtx());
    });

    it("ignores notifications without embedded message", async () => {
      const { callback, bridge } = await startAndCapture();

      await callback("garmin://messages", { conversation_id: "conv-1" });
      await new Promise((r) => setTimeout(r, 10));

      // No type/embedded message → should be silently ignored
      expect(mockDispatch).not.toHaveBeenCalled();
      expect(bridge.readResourceJson).not.toHaveBeenCalled();

      await garminPlugin.gateway!.stopAccount!(makeGatewayCtx());
    });
  });

  describe("setup adapter", () => {
    it("applyAccountConfig enables channel with minimal input", () => {
      const cfg = garminPlugin.setup!.applyAccountConfig({ cfg: {}, accountId: "default", input: {} });
      expect(cfg.channels["garmin-messenger"].enabled).toBe(true);
    });

    it("applyAccountConfig maps authDir to sessionDir", () => {
      const cfg = garminPlugin.setup!.applyAccountConfig({
        cfg: {},
        accountId: "default",
        input: { authDir: "/custom/session" },
      });
      expect(cfg.channels["garmin-messenger"].sessionDir).toBe("/custom/session");
    });

    it("applyAccountConfig maps cliPath to binaryPath", () => {
      const cfg = garminPlugin.setup!.applyAccountConfig({
        cfg: {},
        accountId: "default",
        input: { cliPath: "/usr/bin/garmin-messenger" },
      });
      expect(cfg.channels["garmin-messenger"].binaryPath).toBe("/usr/bin/garmin-messenger");
    });

    it("applyAccountConfig preserves existing config", () => {
      const cfg = garminPlugin.setup!.applyAccountConfig({
        cfg: { channels: { "garmin-messenger": { dmPolicy: "open" } } },
        accountId: "default",
        input: { name: "my-garmin" },
      });
      expect(cfg.channels["garmin-messenger"].dmPolicy).toBe("open");
      expect(cfg.channels["garmin-messenger"].enabled).toBe(true);
      expect(cfg.channels["garmin-messenger"].name).toBe("my-garmin");
    });

    it("validateInput returns null when binary is resolvable", () => {
      expect(garminPlugin.setup!.validateInput!({ cfg: {}, accountId: "default", input: {} })).toBeNull();
    });

    it("validateInput returns error when binary not resolvable", () => {
      mockResolveBinary.mockImplementationOnce(() => { throw new Error("not found"); });
      const result = garminPlugin.setup!.validateInput!({
        cfg: {},
        accountId: "default",
        input: { cliPath: "/nonexistent/binary" },
      });
      expect(result).toContain("binary not found");
    });
  });

  describe("agentPrompt with login instructions", () => {
    it("includes login instructions in messageToolHints", () => {
      const hints = garminPlugin.agentPrompt!.messageToolHints!({ cfg: {} });
      expect(hints.some((h) => /garmin_login/i.test(h))).toBe(true);
      expect(hints.some((h) => /request_otp/i.test(h))).toBe(true);
      expect(hints.some((h) => /confirm_otp/i.test(h))).toBe(true);
    });
  });

  describe("onboarding adapter", () => {
    it("is wired on garminPlugin", () => {
      expect(garminPlugin.onboarding).toBeDefined();
      expect(garminPlugin.onboarding!.channel).toBe("garmin-messenger");
    });
  });

  describe("agentTools", () => {
    it("is a function that returns tools", () => {
      expect(typeof garminPlugin.agentTools).toBe("function");
      const tools = (garminPlugin.agentTools as Function)({});
      expect(Array.isArray(tools)).toBe(true);
      expect(tools.length).toBeGreaterThan(0);
      expect(tools[0].name).toBe("garmin_login");
    });
  });

  describe("login", () => {
    function mockNotLoggedIn() {
      const MockBridge = vi.mocked(MCPBridge);
      let bridge: any;
      MockBridge.mockImplementationOnce(function () {
        bridge = {
          connected: false,
          connect: vi.fn(async function (this: { connected: boolean }) { this.connected = true; }),
          disconnect: vi.fn(async function (this: { connected: boolean }) { this.connected = false; }),
          getStatus: vi.fn(async () => ({ logged_in: false, listening: false })),
          startListening: vi.fn(async () => ({ isError: false, text: '{"listening":true}', json: { listening: true } })),
          stopListening: vi.fn(async () => ({ isError: false, text: '{"listening":false}', json: { listening: false } })),
          sendMessage: vi.fn(),
          sendMediaMessage: vi.fn(),
          requestOtp: vi.fn(async () => ({
            isError: false,
            text: '{"request_id":"req-123","valid_until":"2026-02-08T12:00:00Z","attempts_remaining":3}',
            json: { request_id: "req-123", valid_until: "2026-02-08T12:00:00Z", attempts_remaining: 3 },
          })),
          confirmOtp: vi.fn(async () => ({
            isError: false,
            text: '{"success":true,"instance_id":"new-instance","fcm":"FCM push notifications registered"}',
            json: { success: true, instance_id: "new-instance", fcm: "FCM push notifications registered" },
          })),
          readResourceJson: vi.fn(async () => ({ members: {}, conversations: [], addresses: {} })),
          subscribe: vi.fn(async () => {}),
        };
        return bridge;
      });
      return () => bridge;
    }

    it("loginWithOtpRequest returns OTP details", async () => {
      mockNotLoggedIn();
      const ctx = makeGatewayCtx();
      await garminPlugin.gateway!.startAccount!(ctx);

      const result = await garminPlugin.gateway!.loginWithOtpRequest!(DEFAULT_ACCOUNT_ID, "+15555550100");
      expect(result.ok).toBe(true);
      expect(result.requestId).toBe("req-123");
      expect(result.attemptsRemaining).toBe(3);
      expect(result.validUntil).toBe("2026-02-08T12:00:00Z");

      await garminPlugin.gateway!.stopAccount!(ctx);
    });

    it("loginWithOtpRequest passes deviceName when provided", async () => {
      const getBridge = mockNotLoggedIn();
      const ctx = makeGatewayCtx();
      await garminPlugin.gateway!.startAccount!(ctx);

      await garminPlugin.gateway!.loginWithOtpRequest!(DEFAULT_ACCOUNT_ID, "+15555550100", "my-device");
      expect(getBridge().requestOtp).toHaveBeenCalledWith("+15555550100", "my-device");

      await garminPlugin.gateway!.stopAccount!(ctx);
    });

    it("loginWithOtpRequest fails for unstarted account", async () => {
      await expect(
        garminPlugin.gateway!.loginWithOtpRequest!("unknown", "+15555550100"),
      ).rejects.toThrow("Account unknown not started");
    });

    it("loginWithOtpConfirm completes login and returns instanceId", async () => {
      mockNotLoggedIn();
      const ctx = makeGatewayCtx();
      await garminPlugin.gateway!.startAccount!(ctx);

      const result = await garminPlugin.gateway!.loginWithOtpConfirm!(DEFAULT_ACCOUNT_ID, "+15555550100", "req-123", "123456");
      expect(result.ok).toBe(true);
      expect(result.instanceId).toBe("new-instance");
      expect(result.fcmStatus).toBe("FCM push notifications registered");

      await garminPlugin.gateway!.stopAccount!(ctx);
    });

    it("loginWithOtpConfirm updates instanceId and starts listening", async () => {
      const getBridge = mockNotLoggedIn();
      const ctx = makeGatewayCtx();
      await garminPlugin.gateway!.startAccount!(ctx);

      await garminPlugin.gateway!.loginWithOtpConfirm!(DEFAULT_ACCOUNT_ID, "+15555550100", "req-123", "123456");

      // Should have started listening after login
      expect(getBridge().startListening).toHaveBeenCalled();

      // After confirm, probe should reflect login state
      getBridge().getStatus = vi.fn(async () => ({
        logged_in: true,
        listening: true,
        instance_id: "new-instance",
      }));
      const probeResult = await garminPlugin.status!.probeAccount!({
        account: makeAccount(),
        timeoutMs: 5000,
        cfg: {},
      });
      expect((probeResult as any).instanceId).toBe("new-instance");

      await garminPlugin.gateway!.stopAccount!(ctx);
    });

    it("loginWithOtpConfirm fails for unstarted account", async () => {
      await expect(
        garminPlugin.gateway!.loginWithOtpConfirm!("unknown", "+15555550100", "req-123", "123456"),
      ).rejects.toThrow("Account unknown not started");
    });
  });
});
