import { describe, it, expect, vi, beforeEach } from "vitest";
import { createGarminAgentTools, setAccountsRef } from "./agent-tools.ts";
import type { AccountStateRef } from "./agent-tools.ts";

// Mock runtime for post-login setup
vi.mock("./runtime.ts", () => ({
  getGarminRuntime: () => ({
    logging: {
      getChildLogger: () => ({
        debug: vi.fn(),
        info: vi.fn(),
        warn: vi.fn(),
        error: vi.fn(),
      }),
    },
  }),
}));

function makeMockBridge(overrides: Partial<AccountStateRef["bridge"]> = {}): AccountStateRef["bridge"] {
  return {
    connected: true,
    getStatus: vi.fn(async () => ({ logged_in: true, listening: true, instance_id: "test-inst" })),
    requestOtp: vi.fn(async () => ({
      isError: false,
      text: '{"request_id":"req-1","valid_until":"2026-02-10T12:00:00Z","attempts_remaining":3}',
      json: { request_id: "req-1", valid_until: "2026-02-10T12:00:00Z", attempts_remaining: 3 },
    })),
    confirmOtp: vi.fn(async () => ({
      isError: false,
      text: '{"instance_id":"new-inst","fcm":"registered"}',
      json: { instance_id: "new-inst", fcm: "registered" },
    })),
    startListening: vi.fn(async () => ({ isError: false, text: "{}", json: {} })),
    subscribe: vi.fn(async () => {}),
    ...overrides,
  };
}

describe("createGarminAgentTools", () => {
  let accounts: Map<string, AccountStateRef>;

  beforeEach(() => {
    vi.clearAllMocks();
    accounts = new Map();
    setAccountsRef(accounts);
  });

  it("returns an array with garmin_login tool", () => {
    const tools = createGarminAgentTools({});
    expect(tools).toHaveLength(1);
    expect(tools[0].name).toBe("garmin_login");
    expect(tools[0].label).toBe("Garmin Login");
    expect(tools[0].description).toContain("SMS OTP");
    expect(tools[0].parameters).toBeDefined();
  });

  describe("status action", () => {
    it("returns login state when logged in", async () => {
      const bridge = makeMockBridge();
      accounts.set("default", { bridge, binaryPath: "/usr/bin/garmin-messenger", instanceId: "test-inst" });

      const tool = createGarminAgentTools({})[0];
      const result = await tool.execute("call-1", { action: "status" });

      expect(result.content[0].text).toContain("Connected: yes");
      expect(result.content[0].text).toContain("/usr/bin/garmin-messenger");
      expect(result.content[0].text).toContain("Logged in: true");
      expect(result.content[0].text).toContain("Listening: true");
      expect(result.content[0].text).toContain("Instance ID: test-inst");
      expect(result.content[0].text).not.toContain("request_otp");
    });

    it("returns not logged in state with login hint", async () => {
      const bridge = makeMockBridge({
        getStatus: vi.fn(async () => ({ logged_in: false, listening: false })),
      });
      accounts.set("default", { bridge, binaryPath: "/usr/bin/garmin-messenger" });

      const tool = createGarminAgentTools({})[0];
      const result = await tool.execute("call-2", { action: "status" });

      expect(result.content[0].text).toContain("Connected: yes");
      expect(result.content[0].text).toContain("Logged in: false");
      expect(result.content[0].text).toContain("request_otp");
    });

    it("returns error for account not started", async () => {
      const tool = createGarminAgentTools({})[0];
      const result = await tool.execute("call-3", { action: "status" });

      expect(result.content[0].text).toContain("not running");
      expect(result.content[0].text).toContain("restart");
    });
  });

  describe("request_otp action", () => {
    it("sends OTP and returns request details", async () => {
      const bridge = makeMockBridge();
      accounts.set("default", { bridge });

      const tool = createGarminAgentTools({})[0];
      const result = await tool.execute("call-4", { action: "request_otp", phone: "+15555550100" });

      expect(bridge.requestOtp).toHaveBeenCalledWith("+15555550100", undefined);
      expect(result.content[0].text).toContain("Verification code sent");
      expect(result.content[0].text).toContain("req-1");
    });

    it("passes device_name when provided", async () => {
      const bridge = makeMockBridge();
      accounts.set("default", { bridge });

      const tool = createGarminAgentTools({})[0];
      await tool.execute("call-4b", { action: "request_otp", phone: "+15555550100", device_name: "my-bot" });

      expect(bridge.requestOtp).toHaveBeenCalledWith("+15555550100", "my-bot");
    });

    it("returns error when phone is missing", async () => {
      const bridge = makeMockBridge();
      accounts.set("default", { bridge });

      const tool = createGarminAgentTools({})[0];
      const result = await tool.execute("call-5", { action: "request_otp" });

      expect(result.content[0].text).toContain("'phone' is required");
      expect(bridge.requestOtp).not.toHaveBeenCalled();
    });

    it("returns error text when OTP request fails", async () => {
      const bridge = makeMockBridge({
        requestOtp: vi.fn(async () => ({ isError: true, text: "rate limited", json: null })),
      });
      accounts.set("default", { bridge });

      const tool = createGarminAgentTools({})[0];
      const result = await tool.execute("call-6", { action: "request_otp", phone: "+15555550100" });

      expect(result.content[0].text).toContain("OTP request failed");
      expect(result.content[0].text).toContain("rate limited");
    });
  });

  describe("confirm_otp action", () => {
    it("confirms OTP, starts listening, and returns success", async () => {
      const bridge = makeMockBridge();
      const state: AccountStateRef = { bridge };
      accounts.set("default", state);

      const tool = createGarminAgentTools({})[0];
      const result = await tool.execute("call-7", {
        action: "confirm_otp",
        phone: "+15555550100",
        request_id: "req-1",
        otp_code: "123456",
      });

      expect(bridge.confirmOtp).toHaveBeenCalledWith("req-1", "+15555550100", "123456");
      expect(result.content[0].text).toContain("Login successful");
      expect(result.content[0].text).toContain("new-inst");
      expect(state.instanceId).toBe("new-inst");
      expect(bridge.startListening).toHaveBeenCalled();
      expect(bridge.subscribe).toHaveBeenCalledWith("garmin://messages");
    });

    it("returns error when request_id is missing", async () => {
      const bridge = makeMockBridge();
      accounts.set("default", { bridge });

      const tool = createGarminAgentTools({})[0];
      const result = await tool.execute("call-8", {
        action: "confirm_otp",
        phone: "+15555550100",
        otp_code: "123456",
      });

      expect(result.content[0].text).toContain("'request_id' is required");
    });

    it("returns error when phone is missing", async () => {
      const bridge = makeMockBridge();
      accounts.set("default", { bridge });

      const tool = createGarminAgentTools({})[0];
      const result = await tool.execute("call-9", {
        action: "confirm_otp",
        request_id: "req-1",
        otp_code: "123456",
      });

      expect(result.content[0].text).toContain("'phone' is required");
    });

    it("returns error when otp_code is missing", async () => {
      const bridge = makeMockBridge();
      accounts.set("default", { bridge });

      const tool = createGarminAgentTools({})[0];
      const result = await tool.execute("call-10", {
        action: "confirm_otp",
        request_id: "req-1",
        phone: "+15555550100",
      });

      expect(result.content[0].text).toContain("'otp_code' is required");
    });

    it("returns error text when OTP confirm fails", async () => {
      const bridge = makeMockBridge({
        confirmOtp: vi.fn(async () => ({ isError: true, text: "invalid code", json: null })),
      });
      accounts.set("default", { bridge });

      const tool = createGarminAgentTools({})[0];
      const result = await tool.execute("call-11", {
        action: "confirm_otp",
        phone: "+15555550100",
        request_id: "req-1",
        otp_code: "000000",
      });

      expect(result.content[0].text).toContain("OTP confirmation failed");
      expect(result.content[0].text).toContain("invalid code");
    });
  });

  describe("unknown action", () => {
    it("returns error for unknown action", async () => {
      const bridge = makeMockBridge();
      accounts.set("default", { bridge });

      const tool = createGarminAgentTools({})[0];
      const result = await tool.execute("call-12", { action: "unknown_action" });

      expect(result.content[0].text).toContain("Unknown action");
    });
  });

  describe("custom account_id", () => {
    it("uses provided account_id", async () => {
      const bridge = makeMockBridge();
      accounts.set("my-account", { bridge, binaryPath: "/usr/bin/gm", instanceId: "custom-inst" });

      const tool = createGarminAgentTools({})[0];
      const result = await tool.execute("call-13", { action: "status", account_id: "my-account" });

      expect(result.content[0].text).toContain("Logged in: true");
    });
  });
});
