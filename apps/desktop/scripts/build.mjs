// Bundles the main process, the preload scripts and the renderer into dist/.
import { build } from "esbuild";
import { execFileSync } from "node:child_process";
import { cpSync, mkdirSync } from "node:fs";

const common = { bundle: true, sourcemap: false, logLevel: "warning", legalComments: "none" };
mkdirSync("dist", { recursive: true });
await build({
  ...common,
  entryPoints: { main: "src/main/index.ts" },
  outdir: "dist",
  platform: "node",
  format: "cjs",
  target: "node22",
  external: ["electron"],
  define: { "process.env.EZO_BUILD_SHA": JSON.stringify(process.env.EZO_BUILD_SHA ?? process.env.GITHUB_SHA ?? "dev") },
});
await build({
  ...common,
  entryPoints: { "preload-pill": "src/preload/pill.ts", "preload-settings": "src/preload/settings.ts" },
  outdir: "dist",
  platform: "node",
  format: "cjs",
  target: "node22",
  external: ["electron"],
});
await build({
  ...common,
  entryPoints: { pill: "src/renderer/pill.ts", settings: "src/renderer/settings.ts" },
  outdir: "dist",
  platform: "browser",
  format: "iife",
  target: "chrome140",
});
for (const file of ["pill.html", "pill.css", "settings.html", "settings.css"]) {
  cpSync(`src/renderer/${file}`, `dist/${file}`);
}
// Perception assets (pinned MediaPipe WASM + models, SHA256-verified) and the engine's worker, served from the app origin.
execFileSync(process.execPath, ["../../scripts/vision-assets.mjs", "dist/vision", "--base", "/vision/"], { stdio: "inherit" });
