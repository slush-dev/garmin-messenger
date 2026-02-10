import { garminPlugin, debugLog } from "./src/channel.js";
import { setGarminRuntime } from "./src/runtime.js";
import type { OpenClawPluginApi, OtpRequestResult, OtpConfirmResult } from "./src/types.js";

export type { OtpRequestResult, OtpConfirmResult };
export { garminPlugin, debugLog } from "./src/channel.js";
export { resolveBinary } from "./src/binary.js";
export { MCPBridge } from "./src/mcp-bridge.js";
export { setGarminRuntime, getGarminRuntime } from "./src/runtime.js";

const plugin = {
  id: "garmin-messenger",
  name: "Garmin Messenger",
  description: "Send and receive messages via Garmin Messenger (Hermes protocol)",
  configSchema: {
    type: "object" as const,
    properties: {
      enabled: {
        type: "boolean",
        description: "Enable or disable the Garmin Messenger channel",
        default: false,
      },
      binaryPath: {
        type: "string",
        description: "Explicit path to the garmin-messenger binary (optional — auto-detected from bundled bin/ or PATH)",
      },
      sessionDir: {
        type: "string",
        description: "Directory to store session credentials (optional — defaults to ~/.garmin-messenger)",
      },
      verbose: {
        type: "boolean",
        description: "Enable verbose/debug logging for the MCP server process",
        default: false,
      },
      dmPolicy: {
        type: "string",
        enum: ["open", "pairing", "allowlist"],
        description: "Direct message security policy: 'open' allows anyone, 'pairing' requires approval, 'allowlist' restricts to allowFrom list",
        default: "pairing",
      },
      allowFrom: {
        type: "array",
        items: { type: "string" },
        description: "Phone numbers allowed to message (used with 'allowlist' or 'pairing' dmPolicy)",
      },
    },
  },
  register(api: OpenClawPluginApi): void {
    debugLog("register() called");
    try {
      setGarminRuntime(api.runtime);
      api.registerChannel({ plugin: garminPlugin });
      debugLog("register() OK — channel registered");
    } catch (err) {
      debugLog(`register() FAILED: ${err}\n${(err as Error).stack ?? ""}`);
      throw err;
    }
  },
};

export default plugin;
