import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Build identity for the Diagnostics report (numbers and words only); CI passes GITHUB_SHA.
  env: {
    NEXT_PUBLIC_EZO_VERSION: process.env.npm_package_version ?? "0.1.0",
    NEXT_PUBLIC_EZO_BUILD_SHA: (process.env.EZO_BUILD_SHA ?? process.env.GITHUB_SHA ?? "dev").slice(0, 12),
  },
  // Workspace packages are shipped as TypeScript source.
  transpilePackages: ["@ezo/ui", "@ezo/shared", "@ezo/avatar", "@ezo/perception-client"],
  // Produces a small self-contained server for the Docker image.
  output: "standalone",
  poweredByHeader: false,
  // Do not generate AGENTS.md files during `next dev`.
  agentRules: false,
  reactStrictMode: true,
};

export default nextConfig;
