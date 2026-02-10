import { describe, it, expect, vi } from "vitest";
import { MCPBridge, DEFAULT_TIMEOUT_MS } from "./mcp-bridge.ts";

const mockLogger = {
  debug: vi.fn(),
  info: vi.fn(),
  warn: vi.fn(),
  error: vi.fn(),
};

describe("MCPBridge", () => {
  it("initializes as not connected", () => {
    const bridge = new MCPBridge({
      binaryPath: "/nonexistent",
      logger: mockLogger,
    });
    expect(bridge.connected).toBe(false);
  });

  it("throws when calling tool while not connected", async () => {
    const bridge = new MCPBridge({
      binaryPath: "/nonexistent",
      logger: mockLogger,
    });
    await expect(bridge.callTool("test")).rejects.toThrow("not connected");
  });

  it("throws when reading resource while not connected", async () => {
    const bridge = new MCPBridge({
      binaryPath: "/nonexistent",
      logger: mockLogger,
    });
    await expect(bridge.readResource("garmin://status")).rejects.toThrow("not connected");
  });

  it("throws when downloading media while not connected", async () => {
    const bridge = new MCPBridge({
      binaryPath: "/nonexistent",
      logger: mockLogger,
    });
    await expect(bridge.downloadMedia("conv-1", "msg-1", "/tmp/out")).rejects.toThrow("not connected");
  });

  it("throws when sending message while not connected", async () => {
    const bridge = new MCPBridge({
      binaryPath: "/nonexistent",
      logger: mockLogger,
    });
    await expect(bridge.sendMessage(["+1555"], "hi")).rejects.toThrow("not connected");
  });

  it("exports DEFAULT_TIMEOUT_MS", () => {
    expect(DEFAULT_TIMEOUT_MS).toBe(30_000);
  });

  it("accepts custom timeoutMs option", () => {
    const bridge = new MCPBridge({
      binaryPath: "/nonexistent",
      logger: mockLogger,
      timeoutMs: 5000,
    });
    // Just verifying it constructs without error
    expect(bridge.connected).toBe(false);
  });

  it("disconnect is idempotent when not connected", async () => {
    const bridge = new MCPBridge({
      binaryPath: "/nonexistent",
      logger: mockLogger,
    });
    // Should not throw
    await bridge.disconnect();
    expect(bridge.connected).toBe(false);
  });

  it("accepts onDisconnected option", () => {
    const onDisconnected = vi.fn();
    const bridge = new MCPBridge({
      binaryPath: "/nonexistent",
      logger: mockLogger,
      onDisconnected,
    });
    // Just verifying it constructs without error
    expect(bridge.connected).toBe(false);
  });
});
