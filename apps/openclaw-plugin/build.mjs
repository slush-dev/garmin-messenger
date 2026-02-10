import { build } from "esbuild";

await build({
  entryPoints: ["index.ts"],
  bundle: true,
  format: "cjs",
  platform: "node",
  outfile: "dist/index.cjs",
  external: ["node:*"],
  // import.meta.url is unavailable in CJS — polyfill via __filename
  banner: {
    js: 'var __import_meta_url = require("node:url").pathToFileURL(__filename).href;',
  },
  define: {
    "import.meta.url": "__import_meta_url",
  },
});
