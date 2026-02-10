// Plain-JS postinstall script — runs under bare `node` (no jiti / tsx).
// Inlines platform constants so there are no .ts imports.

import { createWriteStream, chmodSync, existsSync, mkdirSync, readFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { get as httpGet } from "node:http";
import { get as httpsGet } from "node:https";

const BINARY_NAME = "garmin-messenger";
const GITHUB_REPO = "slush-dev/garmin-messenger";
const MAX_REDIRECTS = 5;

function platformSuffix() {
  const os = process.platform === "win32" ? "windows" : process.platform;
  const archMap = { x64: "amd64", arm64: "arm64" };
  const arch = archMap[process.arch] ?? process.arch;
  const ext = process.platform === "win32" ? ".exe" : "";
  return `${os}-${arch}${ext}`;
}

export function buildDownloadURL(version, suffix) {
  return `https://github.com/${GITHUB_REPO}/releases/download/v${version}/${BINARY_NAME}-${suffix}`;
}

export function downloadBinary(url, destPath) {
  return new Promise((resolve, reject) => {
    let redirects = 0;

    function follow(currentUrl) {
      if (redirects > MAX_REDIRECTS) {
        reject(new Error("Too many redirects"));
        return;
      }

      const getter = currentUrl.startsWith("https://") ? httpsGet : httpGet;

      getter(currentUrl, (res) => {
        if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
          redirects++;
          follow(res.headers.location);
          return;
        }

        if (res.statusCode !== 200) {
          res.resume();
          reject(new Error(`Download failed: HTTP ${res.statusCode}`));
          return;
        }

        mkdirSync(dirname(destPath), { recursive: true });
        const file = createWriteStream(destPath);
        res.pipe(file);
        file.on("finish", () => {
          file.close(() => {
            chmodSync(destPath, 0o755);
            resolve();
          });
        });
        file.on("error", (err) => {
          reject(err);
        });
      }).on("error", (err) => {
        reject(err);
      });
    }

    follow(url);
  });
}

async function main() {
  const __dirname = dirname(fileURLToPath(import.meta.url));
  const pkgPath = join(__dirname, "..", "package.json");
  const pkg = JSON.parse(readFileSync(pkgPath, "utf-8"));
  const version = pkg.version;

  const suffix = platformSuffix();
  const binDir = join(__dirname, "..", "bin");
  const destPath = join(binDir, `${BINARY_NAME}-${suffix}`);

  if (existsSync(destPath)) {
    console.log(`[garmin-messenger] Binary already exists: ${destPath}`);
    return;
  }

  const url = buildDownloadURL(version, suffix);
  console.log(`[garmin-messenger] Downloading ${url}`);

  try {
    await downloadBinary(url, destPath);
    console.log(`[garmin-messenger] Installed to ${destPath}`);
  } catch (err) {
    console.warn(
      `[garmin-messenger] Failed to download binary: ${err instanceof Error ? err.message : err}\n` +
        `  The plugin will try to find '${BINARY_NAME}' on your PATH instead.`,
    );
  }
}

main();
