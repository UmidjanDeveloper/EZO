import type { NextConfig } from "next";
import { apiProxyTarget } from "./lib/runtime-config";

const proxyTarget = apiProxyTarget(process.env);

const nextConfig: NextConfig = {
  // Explicit preview deployment option: browser requests stay same-origin while Next
  // forwards them to the local API. Production without this variable is unchanged.
  async rewrites() {
    return proxyTarget ? [{ source: "/api/:path*", destination: `${proxyTarget}/api/:path*` }] : [];
  },
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
