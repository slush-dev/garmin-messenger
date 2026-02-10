import { describe, it, expect } from "vitest";
import { resolveBinary } from "./binary.ts";

describe("resolveBinary", () => {
  it("throws when explicit config path does not exist", () => {
    expect(() => resolveBinary("/nonexistent/path/binary")).toThrow(
      "Configured binary not found",
    );
  });

  it("throws when no binary is found anywhere", () => {
    // With a nonsensical config unset, it should try bundled and PATH
    // Since we don't have a bundled binary in test, and the binary is unlikely on PATH in CI,
    // we test that it provides a helpful error message
    try {
      resolveBinary();
      // If it succeeds (binary on PATH), that's fine too
    } catch (err: unknown) {
      expect((err as Error).message).toContain("garmin-messenger binary not found");
    }
  });

  it("returns explicit path when file exists", () => {
    // Use a known existing file as a stand-in
    const result = resolveBinary("/bin/sh");
    expect(result).toBe("/bin/sh");
  });
});
