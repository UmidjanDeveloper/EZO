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
};

export default nextConfig;
