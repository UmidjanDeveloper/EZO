import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Build identity for the Diagnostics report (numbers and words only); CI passes GITHUB_SHA.
  env: {
    NEXT_PUBLIC_EZO_VERSION: process.env.npm_package_version ?? "0.1.0",
    NEXT_PUBLIC_EZO_BUILD_SHA: (process.env.EZO_BUILD_SHA ?? process.env.GITHUB_SHA ?? "dev").slice(0, 12),
  },
  // Workspace packages are shipped as TypeScript source.
  transpilePackages: ["@ezo/ui", "@ezo/shared", "@ezo/avatar", "@ezo/face-tracking", "@ezo/perception-client"],
  // Produces a small self-contained server for the Docker image.
  output: "standalone",
  poweredByHeader: false,
  // Do not generate AGENTS.md files during `next dev`.
  agentRules: false,
  reactStrictMode: true,
  // Production builds use webpack (`next build --webpack`, see package.json): with
  // @ezo/face-tracking in the graph — its `new Worker(new URL("./vision.worker.ts",
  // import.meta.url))` entry pulls the 1 MB MediaPipe bundle — Turbopack 16.4 never finishes
  // (reproduced with and without public/vision; an alias to lib/vision-worker-stub.ts did not
  // help), while webpack compiles the same app in about 20 s. The web app never loads that
  // worker entry anyway: it serves the engine's worker pre-bundled at /vision/vision.worker.js.
  turbopack: {
    resolveAlias: { "@mediapipe/tasks-vision": "./lib/vision-worker-stub.ts" },
  },
};

export default nextConfig;
