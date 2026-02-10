import { createInterface } from "node:readline";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import { ResourceUpdatedNotificationSchema } from "@modelcontextprotocol/sdk/types.js";
import type { ChannelLogSink, GarminStatus } from "./types.ts";
import { debugLog } from "./debug.js";

export type ResourceUpdatedHandler = (uri: string, meta?: Record<string, unknown>) => void;

export const DEFAULT_TIMEOUT_MS = 30_000;

export interface MCPBridgeOptions {
  binaryPath: string;
  sessionDir?: string;
  verbose?: boolean;
  logger: ChannelLogSink;
  onResourceUpdated?: ResourceUpdatedHandler;
  onDisconnected?: () => void;
  timeoutMs?: number;
}

export class MCPBridge {
  private client: Client | null = null;
  private transport: StdioClientTransport | null = null;
  private logger: ChannelLogSink;
  private opts: MCPBridgeOptions;

  constructor(opts: MCPBridgeOptions) {
    this.opts = opts;
    this.logger = opts.logger;
  }

  async connect(): Promise<void> {
    if (this.client) return;

    const args = ["mcp"];
    if (this.opts.sessionDir) args.push("--session-dir", this.opts.sessionDir);
    if (this.opts.verbose) args.push("--verbose");

    debugLog(`[mcp] spawning: ${this.opts.binaryPath} ${args.join(" ")}`);
    this.logger.debug?.(`Spawning MCP: ${this.opts.binaryPath} ${args.join(" ")}`);

    this.transport = new StdioClientTransport({
      command: this.opts.binaryPath,
      args,
      stderr: "pipe",
    });

    // Pipe subprocess stderr into debug log
    if (this.transport.stderr) {
      const rl = createInterface({ input: this.transport.stderr as NodeJS.ReadableStream });
      rl.on("line", (line) => {
        debugLog(`[binary] ${line}`);
      });
    }

    this.client = new Client(
      { name: "openclaw-garmin", version: "0.1.0" },
    );

    if (this.opts.onResourceUpdated) {
      const handler = this.opts.onResourceUpdated;
      debugLog(`[mcp] registering ResourceUpdatedNotification handler`);
      this.client.setNotificationHandler(
        ResourceUpdatedNotificationSchema,
        (notification) => {
          debugLog(`[mcp] ResourceUpdatedNotification received: ${JSON.stringify(notification.params)}`);
          const uri = notification.params?.uri;
          if (uri) {
            handler(uri, notification.params?._meta as Record<string, unknown> | undefined);
          } else {
            debugLog(`[mcp] notification had no URI, ignoring`);
          }
        },
      );
    } else {
      debugLog(`[mcp] WARNING: no onResourceUpdated handler provided`);
    }

    this.transport.onclose = () => {
      debugLog(`[mcp] transport closed unexpectedly`);
      this.logger.warn("MCP transport closed unexpectedly");
      this.client = null;
      this.transport = null;
      this.opts.onDisconnected?.();
    };
    this.transport.onerror = (err) => {
      debugLog(`[mcp] transport error: ${err}`);
      this.logger.error(`MCP transport error: ${err}`);
      this.client = null;
      this.transport = null;
      this.opts.onDisconnected?.();
    };

    await this.client.connect(this.transport);
    debugLog(`[mcp] connected OK`);
    this.logger.info("MCP bridge connected");
  }

  async disconnect(): Promise<void> {
    if (!this.client) return;
    debugLog(`[mcp] disconnecting...`);
    try {
      await this.transport?.close();
    } catch (err) {
      debugLog(`[mcp] transport close error: ${err}`);
      this.logger.warn(`Transport close error: ${err}`);
    }
    this.client = null;
    this.transport = null;
    debugLog(`[mcp] disconnected`);
    this.logger.info("MCP bridge disconnected");
  }

  get connected(): boolean {
    return this.client !== null;
  }

  async callTool(name: string, args: Record<string, unknown> = {}): Promise<ToolResult> {
    if (!this.client) throw new Error("MCP bridge not connected");
    debugLog(`[mcp] callTool(${name}, ${JSON.stringify(args).slice(0, 200)})`);
    const result = await withTimeout(
      this.client.callTool({ name, arguments: args }),
      this.opts.timeoutMs ?? DEFAULT_TIMEOUT_MS,
      `callTool(${name})`,
    );
    const text = (result.content as Array<{ type: string; text: string }>)
      .filter((c) => c.type === "text")
      .map((c) => c.text)
      .join("");
    const isError = !!(result as { isError?: boolean }).isError;
    debugLog(`[mcp] callTool(${name}) → isError=${isError} text=${text.slice(0, 200)}`);
    return {
      isError,
      text,
      json: safeJsonParse(text),
    };
  }

  async readResource(uri: string): Promise<string> {
    if (!this.client) throw new Error("MCP bridge not connected");
    debugLog(`[mcp] readResource(${uri})`);
    const result = await withTimeout(
      this.client.readResource({ uri }),
      this.opts.timeoutMs ?? DEFAULT_TIMEOUT_MS,
      `readResource(${uri})`,
    );
    const text = (result.contents[0] as { text?: string })?.text ?? "";
    debugLog(`[mcp] readResource(${uri}) → ${text.slice(0, 300)}`);
    return text;
  }

  async readResourceJson<T = unknown>(uri: string): Promise<T> {
    const text = await this.readResource(uri);
    return JSON.parse(text);
  }

  async getStatus(): Promise<GarminStatus> {
    return this.readResourceJson<GarminStatus>("garmin://status");
  }

  async startListening(noCatchup?: boolean): Promise<ToolResult> {
    const args: Record<string, unknown> = {};
    if (noCatchup) args.no_catchup = true;
    return this.callTool("listen", args);
  }

  async stopListening(): Promise<ToolResult> {
    return this.callTool("stop");
  }

  async subscribe(uri: string): Promise<void> {
    if (!this.client) throw new Error("MCP bridge not connected");
    await this.client.subscribeResource({ uri });
  }

  async sendMessage(to: string[], body: string): Promise<ToolResult> {
    return this.callTool("send_message", { to, body });
  }

  async requestOtp(phone: string, deviceName?: string): Promise<ToolResult> {
    const args: Record<string, unknown> = { phone };
    if (deviceName) args.device_name = deviceName;
    return this.callTool("login_request_otp", args);
  }

  async confirmOtp(requestId: string, phone: string, otpCode: string): Promise<ToolResult> {
    return this.callTool("login_confirm_otp", { request_id: requestId, phone, otp_code: otpCode });
  }

  async downloadMedia(
    conversationId: string,
    messageId: string,
    outputPath: string,
  ): Promise<{ filePath: string; bytes: number; mediaType: string }> {
    const result = await this.callTool("download_media", {
      conversation_id: conversationId,
      message_id: messageId,
      output_path: outputPath,
    });
    if (result.isError) throw new Error(result.text);
    const data = result.json as { file_path: string; bytes: number; media_type: string };
    return { filePath: data.file_path, bytes: data.bytes, mediaType: data.media_type };
  }

  async sendMediaMessage(
    to: string[],
    body: string,
    filePath: string,
    mediaType?: string,
  ): Promise<ToolResult> {
    const args: Record<string, unknown> = { to, body, file_path: filePath };
    if (mediaType) args.media_type = mediaType;
    return this.callTool("send_media_message", args);
  }
}

export interface ToolResult {
  isError: boolean;
  text: string;
  json: unknown;
}

function safeJsonParse(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

function withTimeout<T>(promise: Promise<T>, ms: number, label: string): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error(`MCP operation timed out after ${ms}ms: ${label}`)), ms);
    promise.then(
      (v) => { clearTimeout(timer); resolve(v); },
      (e) => { clearTimeout(timer); reject(e); },
    );
  });
}
