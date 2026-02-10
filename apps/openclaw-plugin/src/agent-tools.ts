import { Type } from "@sinclair/typebox";
import type {
  ChannelAgentTool,
  ChannelAgentToolFactory,
  AgentToolResult,
  OpenClawConfig,
} from "./types.js";

// Module-level reference to accounts map — set by channel.ts via setAccountsRef()
let accountsRef: Map<string, AccountStateRef> | null = null;

export interface AccountStateRef {
  bridge: {
    connected: boolean;
    getStatus: () => Promise<{ logged_in: boolean; listening: boolean; instance_id?: string }>;
    requestOtp: (phone: string, deviceName?: string) => Promise<{ isError: boolean; text: string; json: unknown }>;
    confirmOtp: (requestId: string, phone: string, otpCode: string) => Promise<{ isError: boolean; text: string; json: unknown }>;
    startListening: (noCatchup?: boolean) => Promise<{ isError: boolean; text: string; json: unknown }>;
    subscribe: (uri: string) => Promise<void>;
  };
  binaryPath?: string;
  instanceId?: string;
}

export function setAccountsRef(ref: Map<string, AccountStateRef>): void {
  accountsRef = ref;
}

const DEFAULT_ACCOUNT_ID = "default";

function textResult(text: string): AgentToolResult {
  return { content: [{ type: "text", text }], details: undefined };
}

const loginToolSchema = Type.Object({
  action: Type.Union([
    Type.Literal("request_otp"),
    Type.Literal("confirm_otp"),
    Type.Literal("status"),
  ]),
  phone: Type.Optional(Type.String()),
  otp_code: Type.Optional(Type.String()),
  request_id: Type.Optional(Type.String()),
  device_name: Type.Optional(Type.String()),
  account_id: Type.Optional(Type.String()),
});

export const createGarminAgentTools: ChannelAgentToolFactory = (_params: { cfg?: OpenClawConfig }) => {
  const tool: ChannelAgentTool = {
    name: "garmin_login",
    label: "Garmin Login",
    description:
      "Login to Garmin Messenger via SMS OTP. " +
      "First call with action 'status' to check current state. " +
      "If not logged in, ask the user which phone number to use (do NOT assume). " +
      "Then use 'request_otp' with that number to send a code, " +
      "and 'confirm_otp' with the received code.",
    parameters: loginToolSchema,

    async execute(_toolCallId: string, args: unknown): Promise<AgentToolResult> {
      const { action, phone, otp_code, request_id, device_name, account_id } =
        args as {
          action: string;
          phone?: string;
          otp_code?: string;
          request_id?: string;
          device_name?: string;
          account_id?: string;
        };

      const accountId = account_id ?? DEFAULT_ACCOUNT_ID;

      if (!accountsRef) {
        return textResult(
          "Error: Garmin Messenger plugin not initialized. " +
          "Ask the user to restart OpenClaw.",
        );
      }

      const state = accountsRef.get(accountId);
      if (!state) {
        return textResult(
          `Error: Garmin Messenger account "${accountId}" is not running. ` +
          "Ask the user to restart OpenClaw so the gateway can start the account.",
        );
      }

      switch (action) {
        case "status": {
          try {
            const status = await state.bridge.getStatus();
            const lines = [
              `Connected: yes${state.binaryPath ? ` (binary: ${state.binaryPath})` : ""}`,
              `Logged in: ${status.logged_in}`,
              `Listening: ${status.listening}`,
            ];
            if (status.instance_id) lines.push(`Instance ID: ${status.instance_id}`);
            if (!status.logged_in) {
              lines.push("");
              lines.push("Use request_otp to start SMS login.");
            }
            return textResult(lines.join("\n"));
          } catch (err) {
            return textResult(`Error checking status: ${err}`);
          }
        }

        case "request_otp": {
          if (!phone) {
            return textResult("Error: 'phone' is required for request_otp. Ask the user for their phone number in E.164 format (e.g. +15555550100).");
          }
          try {
            const result = await state.bridge.requestOtp(phone, device_name);
            if (result.isError) {
              return textResult(`OTP request failed: ${result.text}`);
            }
            const data = result.json as { request_id?: string; valid_until?: string; attempts_remaining?: number } | null;
            return textResult(
              `Verification code sent to ${phone}.\n` +
              `Request ID: ${data?.request_id ?? "unknown"}\n` +
              `Valid until: ${data?.valid_until ?? "unknown"}\n` +
              `Attempts remaining: ${data?.attempts_remaining ?? "unknown"}\n\n` +
              "Ask the user for the code they received via SMS, then call confirm_otp with the code and this request_id.",
            );
          } catch (err) {
            return textResult(`Error requesting OTP: ${err}`);
          }
        }

        case "confirm_otp": {
          if (!request_id) {
            return textResult("Error: 'request_id' is required for confirm_otp.");
          }
          if (!phone) {
            return textResult("Error: 'phone' is required for confirm_otp.");
          }
          if (!otp_code) {
            return textResult("Error: 'otp_code' is required for confirm_otp. Ask the user for the code they received.");
          }
          try {
            const result = await state.bridge.confirmOtp(request_id, phone, otp_code);
            if (result.isError) {
              return textResult(`OTP confirmation failed: ${result.text}`);
            }
            const data = result.json as { instance_id?: string; fcm?: string } | null;

            // Update instance ID on the account state
            state.instanceId = data?.instance_id;

            // Start listening after successful login
            const listenResult = await state.bridge.startListening();
            if (!listenResult.isError) {
              try {
                await state.bridge.subscribe("garmin://messages");
              } catch {}
            }

            return textResult(
              "Login successful! Garmin Messenger is now connected and listening for messages.\n" +
              (data?.instance_id ? `Instance ID: ${data.instance_id}\n` : "") +
              (data?.fcm ? `FCM: ${data.fcm}` : ""),
            );
          } catch (err) {
            return textResult(`Error confirming OTP: ${err}`);
          }
        }

        default:
          return textResult(`Unknown action: ${action}. Use 'status', 'request_otp', or 'confirm_otp'.`);
      }
    },
  };

  return [tool];
};
