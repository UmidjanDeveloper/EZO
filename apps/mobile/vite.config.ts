import { defineConfig } from "vite";

export default defineConfig({
  build: { outDir: "dist", target: "es2022", sourcemap: false },
  test: { environment: "node", include: ["src/**/*.test.ts"] },
} as Parameters<typeof defineConfig>[0]);
