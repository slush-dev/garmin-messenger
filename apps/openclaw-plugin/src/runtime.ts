import type { PluginRuntime } from "./types.js";

let runtime: PluginRuntime | null = null;

export function setGarminRuntime(next: PluginRuntime): void {
  runtime = next;
}

export function getGarminRuntime(): PluginRuntime {
  if (!runtime) {
    throw new Error("Garmin runtime not initialized");
  }
  return runtime;
}

/** Reset runtime state for tests. */
export function resetGarminRuntime(): void {
  runtime = null;
}
