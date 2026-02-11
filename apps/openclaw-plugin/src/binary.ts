import { execFile as execFileCb, execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";
import { BINARY_NAME, platformSuffix } from "./platform.js";

const execFileAsync = promisify(execFileCb);

function findBundled(): string | null {
  const dir = join(fileURLToPath(import.meta.url), "..", "..", "bin");
  const name = `${BINARY_NAME}-${platformSuffix()}`;
  const full = join(dir, name);
  return existsSync(full) ? full : null;
}

function findOnPath(): string | null {
  const cmd = process.platform === "win32" ? "where" : "which";
  try {
    return execFileSync(cmd, [BINARY_NAME], {
      encoding: "utf-8",
      stdio: ["pipe", "pipe", "ignore"],
    }).trim().split("\n")[0];
  } catch {
    return null;
  }
}

/**
 * Resolve the garmin-messenger binary path (sync).
 * Priority: explicit config → bundled platform binary → PATH lookup.
 */
export function resolveBinary(configPath?: string): string {
  if (configPath) {
    if (!existsSync(configPath)) {
      throw new Error(`Configured binary not found: ${configPath}`);
    }
    return configPath;
  }

  const bundled = findBundled();
  if (bundled) return bundled;

  const onPath = findOnPath();
  if (onPath) return onPath;

  throw new Error(
    `${BINARY_NAME} binary not found. Either:\n` +
      `  1. Set channels.garmin-messenger.binaryPath in config\n` +
      `  2. Place platform binary in apps/openclaw-plugin/bin/\n` +
      `  3. Add ${BINARY_NAME} to your PATH`,
  );
}

/**
 * Resolve the garmin-messenger binary path, downloading it if necessary.
 * Priority: explicit config → bundled binary → run postinstall to download → PATH lookup.
 */
export async function ensureBinary(configPath?: string): Promise<string> {
  if (configPath) {
    if (!existsSync(configPath)) {
      throw new Error(`Configured binary not found: ${configPath}`);
    }
    return configPath;
  }

  const bundled = findBundled();
  if (bundled) return bundled;

  // Binary not bundled — try running postinstall to download it
  const root = join(fileURLToPath(import.meta.url), "..", "..");
  const scriptPath = join(root, "scripts", "postinstall.mjs");
  if (existsSync(scriptPath)) {
    await execFileAsync("node", [scriptPath], {
      cwd: root,
      timeout: 60_000,
    });

    const downloaded = findBundled();
    if (downloaded) return downloaded;
  }

  const onPath = findOnPath();
  if (onPath) return onPath;

  throw new Error(
    `${BINARY_NAME} binary not found. Either:\n` +
      `  1. Set channels.garmin-messenger.binaryPath in config\n` +
      `  2. Place platform binary in apps/openclaw-plugin/bin/\n` +
      `  3. Add ${BINARY_NAME} to your PATH`,
  );
}
