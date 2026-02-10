import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { createServer, type Server, type IncomingMessage, type ServerResponse } from "node:http";
import { existsSync, mkdirSync, readFileSync, rmSync, statSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const testBinDir = join(__dirname, "..", "bin");

describe("platform", () => {
  it("exports BINARY_NAME and GITHUB_REPO", async () => {
    const { BINARY_NAME, GITHUB_REPO } = await import("./platform.js");
    expect(BINARY_NAME).toBe("garmin-messenger");
    expect(GITHUB_REPO).toBe("slush-dev/garmin-messenger");
  });

  it("platformSuffix returns os-arch format", async () => {
    const { platformSuffix } = await import("./platform.js");
    const suffix = platformSuffix();
    expect(suffix).toMatch(/^(linux|darwin|windows)-(amd64|arm64)/);
  });
});

describe("postinstall", () => {
  // Import the internal helpers for testing
  let buildDownloadURL: (version: string, suffix: string) => string;

  beforeEach(async () => {
    const mod = await import("../scripts/postinstall.mjs");
    buildDownloadURL = mod.buildDownloadURL;
  });

  it("buildDownloadURL constructs correct GitHub release URL", () => {
    const url = buildDownloadURL("1.2.0", "linux-amd64");
    expect(url).toBe(
      "https://github.com/slush-dev/garmin-messenger/releases/download/v1.2.0/garmin-messenger-linux-amd64",
    );
  });

  it("buildDownloadURL handles windows .exe suffix", () => {
    const url = buildDownloadURL("1.0.0", "windows-amd64.exe");
    expect(url).toBe(
      "https://github.com/slush-dev/garmin-messenger/releases/download/v1.0.0/garmin-messenger-windows-amd64.exe",
    );
  });

  describe("downloadBinary", () => {
    let server: Server;
    let serverPort: number;
    let downloadBinary: (url: string, destPath: string) => Promise<void>;

    beforeEach(async () => {
      const mod = await import("../scripts/postinstall.mjs");
      downloadBinary = mod.downloadBinary;
      // Clean up any test binaries
      if (existsSync(testBinDir)) {
        rmSync(testBinDir, { recursive: true });
      }
    });

    afterEach(() => {
      if (server) {
        server.close();
      }
    });

    function startServer(handler: (req: IncomingMessage, res: ServerResponse) => void): Promise<number> {
      return new Promise((resolve) => {
        server = createServer(handler);
        server.listen(0, () => {
          const addr = server.address();
          resolve(typeof addr === "object" && addr ? addr.port : 0);
        });
      });
    }

    it("downloads binary and sets executable permissions", async () => {
      const binaryContent = "#!/bin/sh\necho hello";
      serverPort = await startServer((_req, res) => {
        res.writeHead(200, { "Content-Type": "application/octet-stream" });
        res.end(binaryContent);
      });

      const destPath = join(testBinDir, "test-binary");
      mkdirSync(testBinDir, { recursive: true });
      await downloadBinary(`http://127.0.0.1:${serverPort}/binary`, destPath);

      expect(existsSync(destPath)).toBe(true);
      expect(readFileSync(destPath, "utf-8")).toBe(binaryContent);

      const stats = statSync(destPath);
      // Check executable bit is set (owner execute)
      expect(stats.mode & 0o100).toBeTruthy();

      // Cleanup
      rmSync(testBinDir, { recursive: true });
    });

    it("follows redirects", async () => {
      const binaryContent = "binary-data-here";
      serverPort = await startServer((req, res) => {
        if (req.url === "/redirect") {
          res.writeHead(302, { Location: `http://127.0.0.1:${serverPort}/actual` });
          res.end();
        } else {
          res.writeHead(200, { "Content-Type": "application/octet-stream" });
          res.end(binaryContent);
        }
      });

      const destPath = join(testBinDir, "test-redirect-binary");
      mkdirSync(testBinDir, { recursive: true });
      await downloadBinary(`http://127.0.0.1:${serverPort}/redirect`, destPath);

      expect(readFileSync(destPath, "utf-8")).toBe(binaryContent);

      rmSync(testBinDir, { recursive: true });
    });

    it("throws on 404", async () => {
      serverPort = await startServer((_req, res) => {
        res.writeHead(404);
        res.end("Not Found");
      });

      const destPath = join(testBinDir, "test-404");
      mkdirSync(testBinDir, { recursive: true });

      await expect(
        downloadBinary(`http://127.0.0.1:${serverPort}/missing`, destPath),
      ).rejects.toThrow("404");

      rmSync(testBinDir, { recursive: true });
    });

    it("throws on too many redirects", async () => {
      serverPort = await startServer((_req, res) => {
        res.writeHead(302, { Location: `http://127.0.0.1:${serverPort}/loop` });
        res.end();
      });

      const destPath = join(testBinDir, "test-loop");
      mkdirSync(testBinDir, { recursive: true });

      await expect(
        downloadBinary(`http://127.0.0.1:${serverPort}/loop`, destPath),
      ).rejects.toThrow("Too many redirects");

      rmSync(testBinDir, { recursive: true });
    });
  });
});
