import { describe, it, expect, vi, beforeEach } from "vitest";

// Mock binary resolution
vi.mock("./binary.ts", () => ({
  resolveBinary: vi.fn(() => "/mock/garmin-messenger"),
  ensureBinary: vi.fn(async () => "/mock/garmin-messenger"),
}));

// Mock MCPBridge
const mockBridgeInstance = {
  connected: false,
  connect: vi.fn(async function () { mockBridgeInstance.connected = true; }),
  disconnect: vi.fn(async function () { mockBridgeInstance.connected = false; }),
  getStatus: vi.fn(async () => ({ logged_in: true, listening: false })),
  requestOtp: vi.fn(async () => ({
    isError: false,
    text: '{"request_id":"req-abc"}',
    json: { request_id: "req-abc" },
  })),
  confirmOtp: vi.fn(async () => ({
    isError: false,
    text: '{"instance_id":"inst-1"}',
    json: { instance_id: "inst-1" },
  })),
};

vi.mock("./mcp-bridge.ts", () => ({
  MCPBridge: vi.fn(() => mockBridgeInstance),
}));

import { garminOnboardingAdapter } from "./onboarding.ts";
import { resolveBinary, ensureBinary } from "./binary.ts";
import type {
  WizardPrompter,
  ChannelOnboardingConfigureContext,
  ChannelOnboardingStatusContext,
  RuntimeEnv,
} from "./types.ts";

function makePrompter(overrides: Partial<WizardPrompter> = {}): WizardPrompter {
  return {
    intro: vi.fn(async () => {}),
    outro: vi.fn(async () => {}),
    note: vi.fn(async () => {}),
    select: vi.fn(async () => undefined as any),
    text: vi.fn(async () => ""),
    confirm: vi.fn(async () => true),
    progress: vi.fn(() => ({ update: vi.fn(), stop: vi.fn() })),
    ...overrides,
  };
}

const mockRuntime: RuntimeEnv = {
  log: vi.fn(),
  error: vi.fn(),
  exit: vi.fn() as any,
};

function makeStatusCtx(cfg: Record<string, any> = {}): ChannelOnboardingStatusContext {
  return { cfg, accountOverrides: {} };
}

function makeConfigureCtx(
  prompter: WizardPrompter,
  cfg: Record<string, any> = {},
): ChannelOnboardingConfigureContext {
  return {
    cfg,
    runtime: mockRuntime,
    prompter,
    accountOverrides: {},
    shouldPromptAccountIds: false,
    forceAllowFrom: false,
  };
}

describe("garminOnboardingAdapter", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockBridgeInstance.connected = false;
  });

  it("has correct channel id", () => {
    expect(garminOnboardingAdapter.channel).toBe("garmin-messenger");
  });

  describe("getStatus", () => {
    it("returns not configured when channel not enabled", async () => {
      const status = await garminOnboardingAdapter.getStatus(makeStatusCtx({}));
      expect(status.configured).toBe(false);
      expect(status.selectionHint).toBe("not configured");
    });

    it("returns configured when binary found and logged in via RPC", async () => {
      mockBridgeInstance.getStatus.mockResolvedValueOnce({ logged_in: true, listening: false });
      const status = await garminOnboardingAdapter.getStatus(
        makeStatusCtx({ channels: { "garmin-messenger": { enabled: true } } }),
      );
      expect(status.configured).toBe(true);
      expect(status.selectionHint).toBe("configured");
      expect(status.statusLines).toContain("Binary: found");
      expect(status.statusLines).toContain("Session: logged in");
      expect(mockBridgeInstance.disconnect).toHaveBeenCalled();
    });

    it("returns needs login when binary found but not logged in via RPC", async () => {
      mockBridgeInstance.getStatus.mockResolvedValueOnce({ logged_in: false, listening: false });
      const status = await garminOnboardingAdapter.getStatus(
        makeStatusCtx({ channels: { "garmin-messenger": { enabled: true } } }),
      );
      expect(status.configured).toBe(false);
      expect(status.selectionHint).toBe("needs login");
      expect(status.statusLines).toContain("Binary: found");
      expect(status.statusLines).toContain("Session: not logged in");
      expect(mockBridgeInstance.disconnect).toHaveBeenCalled();
    });

    it("returns needs login when bridge connection fails", async () => {
      mockBridgeInstance.connect.mockRejectedValueOnce(new Error("spawn failed"));
      const status = await garminOnboardingAdapter.getStatus(
        makeStatusCtx({ channels: { "garmin-messenger": { enabled: true } } }),
      );
      expect(status.configured).toBe(false);
      expect(status.selectionHint).toBe("needs login");
      expect(status.statusLines).toContain("Binary: found");
      expect(status.statusLines).toContain("Session: not logged in");
    });
  });

  describe("configure", () => {
    it("happy path — completes OTP login and returns enabled config", async () => {
      const prompter = makePrompter({
        text: vi.fn()
          .mockResolvedValueOnce("+15555550100") // phone
          .mockResolvedValueOnce("123456"), // OTP code
      });

      const result = await garminOnboardingAdapter.configure(makeConfigureCtx(prompter));

      expect(result.cfg.channels?.["garmin-messenger"]?.enabled).toBe(true);
      expect(result.cfg.channels?.["garmin-messenger"]?.sessionDir).toBeDefined();
      expect(result.accountId).toBe("default");
      expect(mockBridgeInstance.connect).toHaveBeenCalled();
      expect(mockBridgeInstance.requestOtp).toHaveBeenCalledWith("+15555550100");
      expect(mockBridgeInstance.confirmOtp).toHaveBeenCalledWith("req-abc", "+15555550100", "123456");
      expect(mockBridgeInstance.disconnect).toHaveBeenCalled();
    });

    it("returns unchanged config when OTP request fails", async () => {
      mockBridgeInstance.requestOtp.mockResolvedValueOnce({
        isError: true,
        text: "rate limited",
        json: null,
      });

      const prompter = makePrompter({
        text: vi.fn().mockResolvedValueOnce("+15555550100"),
      });

      const originalCfg = { existing: true };
      const result = await garminOnboardingAdapter.configure(makeConfigureCtx(prompter, originalCfg));

      expect(result.cfg).toEqual(originalCfg);
      expect(result.accountId).toBeUndefined();
      expect(prompter.note).toHaveBeenCalledWith(expect.stringContaining("rate limited"), "Error");
    });

    it("returns unchanged config when OTP confirm fails", async () => {
      mockBridgeInstance.confirmOtp.mockResolvedValueOnce({
        isError: true,
        text: "invalid code",
        json: null,
      });

      const prompter = makePrompter({
        text: vi.fn()
          .mockResolvedValueOnce("+15555550100")
          .mockResolvedValueOnce("999999"),
      });

      const originalCfg = { existing: true };
      const result = await garminOnboardingAdapter.configure(makeConfigureCtx(prompter, originalCfg));

      expect(result.cfg).toEqual(originalCfg);
      expect(result.accountId).toBeUndefined();
      expect(prompter.note).toHaveBeenCalledWith(expect.stringContaining("invalid code"), "Error");
    });

    it("returns unchanged config when binary not found", async () => {
      vi.mocked(resolveBinary).mockImplementationOnce(() => { throw new Error("not found"); });
      vi.mocked(ensureBinary).mockRejectedValueOnce(new Error("not found"));

      const progressStop = vi.fn();
      const prompter = makePrompter({
        progress: vi.fn(() => ({ update: vi.fn(), stop: progressStop })),
      });
      const originalCfg = { existing: true };
      const result = await garminOnboardingAdapter.configure(makeConfigureCtx(prompter, originalCfg));

      expect(result.cfg).toEqual(originalCfg);
      expect(result.accountId).toBeUndefined();
      expect(prompter.progress).toHaveBeenCalledWith("Downloading garmin-messenger binary...");
      expect(progressStop).toHaveBeenCalledWith("Failed");
      expect(prompter.note).toHaveBeenCalledWith(expect.stringContaining("binary not found"), "Missing Binary");
    });

    it("downloads binary with spinner when not bundled", async () => {
      vi.mocked(resolveBinary).mockImplementationOnce(() => { throw new Error("not found"); });
      vi.mocked(ensureBinary).mockResolvedValueOnce("/downloaded/garmin-messenger");

      const progressStop = vi.fn();
      const prompter = makePrompter({
        progress: vi.fn(() => ({ update: vi.fn(), stop: progressStop })),
        text: vi.fn()
          .mockResolvedValueOnce("+15555550100")
          .mockResolvedValueOnce("123456"),
      });

      const result = await garminOnboardingAdapter.configure(makeConfigureCtx(prompter));

      expect(prompter.progress).toHaveBeenCalledWith("Downloading garmin-messenger binary...");
      expect(progressStop).toHaveBeenCalledWith("Binary ready");
      expect(result.cfg.channels?.["garmin-messenger"]?.enabled).toBe(true);
      expect(result.accountId).toBe("default");
    });

    it("disconnects bridge even on error", async () => {
      mockBridgeInstance.connect.mockRejectedValueOnce(new Error("conn failed"));

      const prompter = makePrompter({
        text: vi.fn().mockResolvedValueOnce("+15555550100"),
      });

      const result = await garminOnboardingAdapter.configure(makeConfigureCtx(prompter));

      expect(result.accountId).toBeUndefined();
      expect(mockBridgeInstance.disconnect).toHaveBeenCalled();
    });
  });

  describe("disable", () => {
    it("sets enabled to false", () => {
      const cfg = {
        channels: { "garmin-messenger": { enabled: true, sessionDir: "/tmp" } },
      };
      const result = garminOnboardingAdapter.disable!(cfg);
      expect(result.channels["garmin-messenger"].enabled).toBe(false);
      expect(result.channels["garmin-messenger"].sessionDir).toBe("/tmp");
    });
  });
});
