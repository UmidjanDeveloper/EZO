import { defineConfig } from "vite";

export default defineConfig({
  define: { __EZO_BUILD_SHA__: JSON.stringify(process.env.EZO_BUILD_SHA ?? process.env.GITHUB_SHA ?? "dev"), __EZO_VERSION__: JSON.stringify(process.env.npm_package_version ?? "0.1.0") },
  build: { outDir: "dist", target: "es2022", sourcemap: false },
  test: { environment: "node", include: ["src/**/*.test.ts"] },
} as Parameters<typeof defineConfig>[0]);
