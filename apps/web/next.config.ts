import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Workspace packages are shipped as TypeScript source.
  transpilePackages: ["@ezo/ui", "@ezo/shared", "@ezo/avatar", "@ezo/face-tracking", "@ezo/perception-client"],
  // Produces a small self-contained server for the Docker image.
  output: "standalone",
  poweredByHeader: false,
  // Do not generate AGENTS.md files during `next dev`.
  agentRules: false,
  reactStrictMode: true,
  // The perception engine's own worker entry (new Worker(new URL("./vision.worker.ts")))
  // is never loaded by the web app, which serves the pre-bundled /vision/vision.worker.js
  // instead; the MediaPipe bundle is kept out of that dead worker chunk (Turbopack otherwise
  // stalls on it). See lib/vision-worker-stub.ts.
  turbopack: {
    resolveAlias: { "@mediapipe/tasks-vision": "./lib/vision-worker-stub.ts" },
  },
};

export default nextConfig;
