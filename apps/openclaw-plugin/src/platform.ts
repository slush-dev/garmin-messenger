export const BINARY_NAME = "garmin-messenger";
export const GITHUB_REPO = "slush-dev/garmin-messenger";

export function platformSuffix(): string {
  const os = process.platform === "win32" ? "windows" : process.platform;
  const archMap: Record<string, string> = { x64: "amd64", arm64: "arm64" };
  const arch = archMap[process.arch] ?? process.arch;
  const ext = process.platform === "win32" ? ".exe" : "";
  return `${os}-${arch}${ext}`;
}
