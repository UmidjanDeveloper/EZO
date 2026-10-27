import { defineConfig, devices } from "@playwright/test";
import path from "node:path";

/**
 * End-to-end tests run a real browser against EZO on dedicated ports
 * (web 3100, API 8100) with a fresh SQLite database and no AI keys
 * (offline mode), so results are deterministic and never cost money.
 */
const ROOT = path.resolve(__dirname, "../..");
const PYTHON = process.env.EZO_PYTHON ?? (process.platform === "win32" ? "python" : "python3");
const WEB_PORT = 3100;
const API_PORT = 8100;
const DOCS_PORT = 8200;

export default defineConfig({
  testDir: "./specs",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 30_000,
  expect: { timeout: 10_000 },
  reporter: [["list"], ["junit", { outputFile: "reports/junit.xml" }]],
  use: {
    baseURL: `http://localhost:${WEB_PORT}`,
    trace: "retain-on-failure",
    launchOptions: {
      // GPU-less CI machines render EZO's WebGL humanoid with SwiftShader.
      args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"],
      ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE } : {}),
    },
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] }, testIgnore: /(mobile|perception)\.spec\.ts/ },
    { name: "mobile", use: { ...devices["Pixel 7"] }, testMatch: /mobile\.spec\.ts/ },
    {
      // The real perception engine with Chromium's FAKE camera and a FAKE microphone file
      // (short clap-like bursts): a SIMULATION that proves wiring and cleanup, never a device.
      name: "perception",
      testMatch: /perception\.spec\.ts/,
      use: {
        ...devices["Desktop Chrome"],
        permissions: ["camera", "microphone"],
        launchOptions: {
          args: [
            "--use-angle=swiftshader",
            "--enable-unsafe-swiftshader",
            "--ignore-gpu-blocklist",
            "--use-fake-device-for-media-stream",
            "--use-fake-ui-for-media-stream",
            `--use-file-for-fake-audio-capture=${path.resolve(__dirname, "fixtures/media/fake-claps.wav")}`,
          ],
          ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE } : {}),
        },
      },
    },
  ],
  webServer: [
    {
      command: `${PYTHON} scripts/ezo.py api --e2e --port ${API_PORT}`,
      cwd: ROOT,
      url: `http://localhost:${API_PORT}/api/health`,
      timeout: 120_000,
      reuseExistingServer: false,
      // Private networks are allowed ONLY for this test API, so the Knowledge OS spec can
      // learn the fixture documentation site served on 127.0.0.1 below.
      env: { EZO_CORS_ORIGINS: `http://localhost:${WEB_PORT}`, EZO_FETCH_ALLOW_PRIVATE_NETWORKS: "true" },
    },
    {
      command: `${PYTHON} -m http.server ${DOCS_PORT} --bind 127.0.0.1 --directory tests/e2e/fixtures/docs-site`,
      cwd: ROOT,
      url: `http://127.0.0.1:${DOCS_PORT}/guide/`,
      timeout: 30_000,
      reuseExistingServer: false,
    },
    {
      command: `pnpm --filter @ezo/web build && pnpm --filter @ezo/web exec next start --port ${WEB_PORT}`,
      cwd: ROOT,
      url: `http://localhost:${WEB_PORT}`,
      timeout: 300_000,
      reuseExistingServer: false,
      env: { EZO_API_URL: `http://localhost:${API_PORT}` },
    },
  ],
});
