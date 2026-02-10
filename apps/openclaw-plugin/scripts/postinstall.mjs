// Plain-JS postinstall script — runs under bare `node` (no jiti / tsx).
// Inlines platform constants so there are no .ts imports.

import { createWriteStream, chmodSync, existsSync, mkdirSync, readFileSync, unlinkSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { createHash } from "node:crypto";
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

export function verifyChecksum(filePath, expectedDigest) {
  const data = readFileSync(filePath);
  const actual = createHash("sha256").update(data).digest("hex");
  const expected = expectedDigest.replace(/^sha256:/, "");
  if (actual !== expected) {
    unlinkSync(filePath);
    throw new Error(`Checksum mismatch: expected ${expected}, got ${actual}`);
  }
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
          const location = res.headers.location;
          if (currentUrl.startsWith("https://") && location.startsWith("http://")) {
            res.resume();
            reject(new Error("Refusing HTTPS to HTTP redirect downgrade"));
            return;
          }
          redirects++;
          follow(location);
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

    const checksumsPath = join(__dirname, "..", "checksums.json");
    if (existsSync(checksumsPath)) {
      const checksums = JSON.parse(readFileSync(checksumsPath, "utf-8"));
      const assetName = `${BINARY_NAME}-${suffix}`;
      const expectedDigest = checksums[assetName];
      if (expectedDigest) {
        verifyChecksum(destPath, expectedDigest);
        console.log(`[garmin-messenger] Checksum verified`);
      } else {
        console.warn(`[garmin-messenger] No checksum found for ${assetName}, skipping verification`);
      }
    }

    console.log(`[garmin-messenger] Installed to ${destPath}`);
  } catch (err) {
    console.warn(
      `[garmin-messenger] Failed to download binary: ${err instanceof Error ? err.message : err}\n` +
        `  The plugin will try to find '${BINARY_NAME}' on your PATH instead.`,
    );
  }
}

main();
