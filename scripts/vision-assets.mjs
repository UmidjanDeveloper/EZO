// Prepares the perception assets an app serves from its own origin (no CDN at runtime):
// the pinned MediaPipe WASM runtime (bytes from node_modules), the two official landmark
// models (downloaded once into .cache/, SHA256-verified against scripts/vision/pins.json,
// refused on any mismatch) and the engine's worker bundled by esbuild.
//
//   node scripts/vision-assets.mjs <outDir> [--base /vision/]
//
// Writes <outDir>/vision-assets.json for @ezo/face-tracking's createVisionEstimator.
import { createHash } from "node:crypto";
import { copyFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, "..");
const [outArg, ...rest] = process.argv.slice(2);
if (!outArg) throw new Error("usage: node scripts/vision-assets.mjs <outDir> [--base /vision/]");
const base = rest.includes("--base") ? rest[rest.indexOf("--base") + 1] : "/vision/";
const out = resolve(outArg);
const cache = resolve(root, ".cache/vision-models");
mkdirSync(out, { recursive: true });
mkdirSync(cache, { recursive: true });

const pins = JSON.parse(readFileSync(resolve(here, "vision/pins.json"), "utf8"));
const review = readFileSync(resolve(here, "vision/MODEL_LICENSE_REVIEW.txt"), "utf8");
const sha256 = (bytes) => createHash("sha256").update(bytes).digest("hex");

async function model(pin) {
  const cached = resolve(cache, pin.file);
  if (!existsSync(cached) || sha256(readFileSync(cached)) !== pin.sha256) {
    console.log(`vision-assets: downloading ${pin.file} (${pin.bytes} bytes, pinned)`);
    const response = await fetch(pin.url, { redirect: "error" });
    if (!response.ok) throw new Error(`${pin.file}: HTTP ${response.status}`);
    const bytes = new Uint8Array(await response.arrayBuffer());
    if (bytes.byteLength !== pin.bytes || sha256(bytes) !== pin.sha256) throw new Error(`${pin.file}: SHA256/size mismatch — refusing`);
    writeFileSync(cached, bytes);
  }
  copyFileSync(cached, resolve(out, pin.file));
  return { url: `${base}${pin.file}`, sha256: pin.sha256 };
}

const require = createRequire(resolve(root, "packages/face-tracking/package.json"));
const sdk = dirname(require.resolve("@mediapipe/tasks-vision"));
function wasm(pin) {
  const bytes = readFileSync(resolve(sdk, "wasm", pin.file));
  if (sha256(bytes) !== pin.sha256) throw new Error(`${pin.file}: unexpected SDK bytes — refusing`);
  writeFileSync(resolve(out, pin.file), bytes);
  return { url: `${base}${pin.file}`, sha256: pin.sha256 };
}

const assets = {
  face: await model(pins.models.face),
  hand: await model(pins.models.hand),
  wasmLoader: wasm(pins.wasm.loader),
  wasmBinary: wasm(pins.wasm.binary),
  modelLicenseReview: review.trim(),
};
writeFileSync(resolve(out, "vision-assets.json"), JSON.stringify(assets, null, 2) + "\n");
writeFileSync(resolve(out, "MODEL_LICENSE_REVIEW.txt"), review);

// The engine's worker, as a classic (importScripts-capable) bundle served next to the assets.
const { build } = createRequire(resolve(root, "packages/perception-client/package.json"))("esbuild"); // pinned there
await build({
  entryPoints: [resolve(root, "packages/face-tracking/src/vision.worker.ts")],
  bundle: true,
  format: "iife",
  platform: "browser",
  target: "es2022",
  outfile: resolve(out, "vision.worker.js"),
  logLevel: "warning",
  legalComments: "none",
});
console.log(`vision-assets: ready in ${out} (models + wasm ${Math.round((pins.models.face.bytes + pins.models.hand.bytes) / 1e6 + 10.9)} MB, worker bundled)`);
