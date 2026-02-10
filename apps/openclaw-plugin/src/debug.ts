import { homedir } from "node:os";
import { join } from "node:path";
import { appendFileSync, mkdirSync } from "node:fs";

const DEBUG_LOG = join(homedir(), ".openclaw", "garmin-messenger-debug.log");

export function debugLog(msg: string): void {
  try {
    mkdirSync(join(homedir(), ".openclaw"), { recursive: true });
    appendFileSync(DEBUG_LOG, `[${new Date().toISOString()}] ${msg}\n`);
  } catch {}
}
