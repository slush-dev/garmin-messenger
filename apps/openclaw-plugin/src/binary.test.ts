import { describe, it, expect, vi, beforeEach } from "vitest";
import { resolveBinary, ensureBinary } from "./binary.ts";

describe("resolveBinary", () => {
  it("throws when explicit config path does not exist", () => {
    expect(() => resolveBinary("/nonexistent/path/binary")).toThrow(
      "Configured binary not found",
    );
  });

  it("throws when no binary is found anywhere", () => {
    try {
      resolveBinary();
    } catch (err: unknown) {
      expect((err as Error).message).toContain("garmin-messenger binary not found");
    }
  });

  it("returns explicit path when file exists", () => {
    const result = resolveBinary("/bin/sh");
    expect(result).toBe("/bin/sh");
  });
});

describe("ensureBinary", () => {
  it("returns explicit config path when file exists", async () => {
    const result = await ensureBinary("/bin/sh");
    expect(result).toBe("/bin/sh");
  });

  it("throws when explicit config path does not exist", async () => {
    await expect(ensureBinary("/nonexistent/path/binary")).rejects.toThrow(
      "Configured binary not found",
    );
  });

});

describe("ensureBinary (mocked)", () => {
  let mockExistsSync: ReturnType<typeof vi.fn>;
  let mockExecFile: ReturnType<typeof vi.fn>;
  let mockExecFileSync: ReturnType<typeof vi.fn>;
  let ensureBinaryMocked: typeof ensureBinary;
  let realExistsSync: typeof import("node:fs").existsSync;

  beforeEach(async () => {
    vi.resetModules();

    const realFs = await vi.importActual<typeof import("node:fs")>("node:fs");
    realExistsSync = realFs.existsSync;

    mockExistsSync = vi.fn((p: any) => realExistsSync(p));
    mockExecFile = vi.fn((_cmd: any, _args: any, _opts: any, cb: any) => {
      if (typeof cb === "function") cb(new Error("mock: not called"), "", "");
      return { on: () => {}, removeAllListeners: () => {} };
    });
    mockExecFileSync = vi.fn(() => { throw new Error("not found"); });

    vi.doMock("node:fs", async () => {
      const actual = await vi.importActual<typeof import("node:fs")>("node:fs");
      return { ...actual, existsSync: mockExistsSync };
    });
    vi.doMock("node:child_process", async () => {
      const actual = await vi.importActual<typeof import("node:child_process")>("node:child_process");
      return { ...actual, execFile: mockExecFile, execFileSync: mockExecFileSync };
    });

    const mod = await import("./binary.ts");
    ensureBinaryMocked = mod.ensureBinary;
  });

  it("returns bundled path when binary exists", async () => {
    mockExistsSync.mockImplementation((p: any) => {
      if (String(p).includes("/bin/garmin-messenger-")) return true;
      return realExistsSync(p);
    });

    const result = await ensureBinaryMocked();
    expect(result).toContain("bin/garmin-messenger-");
  });

  it("runs postinstall when bundled binary missing", async () => {
    let bundledCheckCount = 0;

    mockExistsSync.mockImplementation((p: any) => {
      const s = String(p);
      if (s.includes("/bin/garmin-messenger-")) {
        bundledCheckCount++;
        return bundledCheckCount > 1; // not found first, found after postinstall
      }
      if (s.includes("scripts/postinstall.mjs")) return true;
      return realExistsSync(p);
    });

    mockExecFile.mockImplementation((_cmd: any, _args: any, _opts: any, cb: any) => {
      if (typeof cb === "function") cb(null, "", "");
      return { on: () => {}, removeAllListeners: () => {} };
    });

    const result = await ensureBinaryMocked();
    expect(result).toContain("bin/garmin-messenger-");
    expect(mockExecFile).toHaveBeenCalledWith(
      "node",
      expect.arrayContaining([expect.stringContaining("postinstall.mjs")]),
      expect.any(Object),
      expect.any(Function),
    );
  });

  it("falls back to PATH after postinstall fails", async () => {
    mockExistsSync.mockImplementation((p: any) => {
      const s = String(p);
      if (s.includes("/bin/garmin-messenger-")) return false;
      if (s.includes("scripts/postinstall.mjs")) return true;
      return realExistsSync(p);
    });

    // postinstall runs but binary still not found
    mockExecFile.mockImplementation((_cmd: any, _args: any, _opts: any, cb: any) => {
      if (typeof cb === "function") cb(null, "", "");
      return { on: () => {}, removeAllListeners: () => {} };
    });

    // which/where returns a path
    mockExecFileSync.mockReturnValue("/usr/local/bin/garmin-messenger\n");

    const result = await ensureBinaryMocked();
    expect(result).toBe("/usr/local/bin/garmin-messenger");
  });

  it("throws when postinstall and PATH both fail", async () => {
    mockExistsSync.mockImplementation((p: any) => {
      const s = String(p);
      if (s.includes("/bin/garmin-messenger-")) return false;
      if (s.includes("scripts/postinstall.mjs")) return true;
      return realExistsSync(p);
    });

    mockExecFile.mockImplementation((_cmd: any, _args: any, _opts: any, cb: any) => {
      if (typeof cb === "function") cb(null, "", "");
      return { on: () => {}, removeAllListeners: () => {} };
    });

    mockExecFileSync.mockImplementation(() => { throw new Error("not found"); });

    await expect(ensureBinaryMocked()).rejects.toThrow("garmin-messenger binary not found");
  });
});
