import { homedir } from "node:os";
import { join } from "node:path";
import { MCPBridge } from "./mcp-bridge.js";
import { resolveBinary, ensureBinary } from "./binary.js";
import { DEFAULT_ACCOUNT_ID } from "./types.js";
import type {
  ChannelOnboardingAdapter,
  ChannelOnboardingConfigureContext,
  ChannelOnboardingStatusContext,
  ChannelOnboardingStatus,
  ChannelOnboardingResult,
  OpenClawConfig,
} from "./types.js";

const CHANNEL_ID = "garmin-messenger";

function defaultSessionDir(): string {
  return join(homedir(), ".garmin-messenger");
}

/** Check login status by querying the MCP server via RPC. */
async function checkLoggedIn(binaryPath: string, sessionDir: string): Promise<boolean> {
  const bridge = new MCPBridge({
    binaryPath,
    sessionDir,
    logger: { info() {}, warn() {}, error() {} },
  });
  try {
    await bridge.connect();
    const status = await bridge.getStatus();
    return status.logged_in;
  } catch {
    return false;
  } finally {
    try { await bridge.disconnect(); } catch {}
  }
}

export const garminOnboardingAdapter: ChannelOnboardingAdapter = {
  channel: CHANNEL_ID,

  async getStatus(ctx: ChannelOnboardingStatusContext): Promise<ChannelOnboardingStatus> {
    const ch = ctx.cfg.channels?.[CHANNEL_ID];
    const statusLines: string[] = [];

    if (!ch?.enabled) {
      return {
        channel: CHANNEL_ID,
        configured: false,
        statusLines: ["Not configured"],
        selectionHint: "not configured",
      };
    }

    // Check binary
    let binaryPath: string | undefined;
    try {
      binaryPath = resolveBinary(ch.binaryPath);
      statusLines.push("Binary: found");
    } catch {
      statusLines.push("Binary: not found");
    }

    // Check session via RPC
    const sessionDir = ch.sessionDir ?? defaultSessionDir();
    const sessionOk = binaryPath ? await checkLoggedIn(binaryPath, sessionDir) : false;
    statusLines.push(sessionOk ? "Session: logged in" : "Session: not logged in");

    const configured = !!binaryPath && sessionOk;
    return {
      channel: CHANNEL_ID,
      configured,
      statusLines,
      selectionHint: configured ? "configured" : "needs login",
    };
  },

  async configure(ctx: ChannelOnboardingConfigureContext): Promise<ChannelOnboardingResult> {
    const { cfg, prompter } = ctx;

    // Resolve binary (fast path: already available; slow path: download with spinner)
    let binaryPath: string;
    try {
      const chCfg = cfg.channels?.[CHANNEL_ID] ?? {};
      try {
        binaryPath = resolveBinary(chCfg.binaryPath);
      } catch {
        const spinner = prompter.progress("Downloading garmin-messenger binary...");
        try {
          binaryPath = await ensureBinary(chCfg.binaryPath);
          spinner.stop("Binary ready");
        } catch (err) {
          spinner.stop("Failed");
          throw err;
        }
      }
    } catch {
      await prompter.note(
        "garmin-messenger binary not found.\n" +
        "Install it from GitHub Releases or set channels.garmin-messenger.binaryPath in config.",
        "Missing Binary",
      );
      return { cfg };
    }

    // Check if already logged in — skip OTP if session is valid
    const sessionDir = cfg.channels?.[CHANNEL_ID]?.sessionDir ?? defaultSessionDir();
    const alreadyLoggedIn = await checkLoggedIn(binaryPath, sessionDir);
    if (alreadyLoggedIn) {
      await prompter.note("Existing Garmin Messenger session detected — already logged in.", "Session Found");

      const newCfg: OpenClawConfig = {
        ...cfg,
        channels: {
          ...cfg.channels,
          [CHANNEL_ID]: {
            ...cfg.channels?.[CHANNEL_ID],
            enabled: true,
            sessionDir,
          },
        },
      };

      return { cfg: newCfg, accountId: DEFAULT_ACCOUNT_ID };
    }

    // Prompt for phone number
    const phone = await prompter.text({
      message: "Phone number for Garmin Messenger login (E.164 format, e.g. +15555550100):",
      placeholder: "+1...",
      validate: (value) => {
        if (!/^\+\d{7,15}$/.test(value.trim())) {
          return "Phone number must be in E.164 format (e.g. +15555550100)";
        }
        return undefined;
      },
    });

    // Create temporary bridge for OTP flow
    const bridge = new MCPBridge({
      binaryPath,
      sessionDir,
      logger: { info() {}, warn() {}, error() {} },
    });

    try {
      const spinner = prompter.progress("Connecting to Garmin Messenger...");
      await bridge.connect();
      spinner.stop("Connected");

      // Request OTP
      const otpSpinner = prompter.progress("Requesting verification code...");
      const otpResult = await bridge.requestOtp(phone.trim());
      if (otpResult.isError) {
        otpSpinner.stop("Failed");
        await prompter.note(`OTP request failed: ${otpResult.text}`, "Error");
        return { cfg };
      }
      const otpData = otpResult.json as { request_id?: string } | null;
      const requestId = otpData?.request_id;
      otpSpinner.stop("Code sent");

      await prompter.note("Check your phone for the SMS verification code.", "Verification");

      // Prompt for OTP code
      const otpCode = await prompter.text({
        message: "Enter the verification code from SMS:",
        validate: (value) => {
          if (!/^\d{4,8}$/.test(value.trim())) {
            return "Code must be 4-8 digits";
          }
          return undefined;
        },
      });

      // Confirm OTP
      const confirmSpinner = prompter.progress("Verifying code...");
      const confirmResult = await bridge.confirmOtp(requestId ?? "", phone.trim(), otpCode.trim());
      if (confirmResult.isError) {
        confirmSpinner.stop("Failed");
        await prompter.note(`Verification failed: ${confirmResult.text}`, "Error");
        return { cfg };
      }
      confirmSpinner.stop("Verified");

      // Warn if FCM registration failed (push notifications won't work)
      const confirmData = confirmResult.json as { fcm?: string } | null;
      if (confirmData?.fcm && !confirmData.fcm.includes("registered")) {
        await prompter.note(confirmData.fcm, "FCM Warning");
      }

      await prompter.note("Successfully logged in to Garmin Messenger!", "Success");

      const newCfg: OpenClawConfig = {
        ...cfg,
        channels: {
          ...cfg.channels,
          [CHANNEL_ID]: {
            ...cfg.channels?.[CHANNEL_ID],
            enabled: true,
            sessionDir,
          },
        },
      };

      return { cfg: newCfg, accountId: DEFAULT_ACCOUNT_ID };
    } catch (err) {
      await prompter.note(`Unexpected error: ${err}`, "Error");
      return { cfg };
    } finally {
      try {
        await bridge.disconnect();
      } catch {}
    }
  },

  disable(cfg: OpenClawConfig): OpenClawConfig {
    return {
      ...cfg,
      channels: {
        ...cfg.channels,
        [CHANNEL_ID]: {
          ...cfg.channels?.[CHANNEL_ID],
          enabled: false,
        },
      },
    };
  },
};
