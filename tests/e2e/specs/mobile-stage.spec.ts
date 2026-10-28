import { expect, test, type Page } from "@playwright/test";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";

// The built Android web app (apps/mobile/dist) served from memory on a fake origin, as the
// WebView loads it, without a server: the voice stage must open and show the humanoid, with
// no camera at all; the clap microphone stays off until pressed. The clap itself runs in
// clap.spec.ts (project "clap", SIMULATED microphone). Nothing here is a phone.

const MOBILE_DIST = path.resolve(__dirname, "../../../apps/mobile/dist");
const TYPES: Record<string, string> = { ".js": "text/javascript", ".css": "text/css", ".json": "application/json", ".txt": "text/plain" };

async function serveMobile(page: Page) {
  await page.route("http://ezo-mobile.test/**", (route) => {
    const pathname = new URL(route.request().url()).pathname.replace(/^\/$/, "/index.html");
    const file = path.join(MOBILE_DIST, pathname);
    if (!existsSync(file)) return route.fulfill({ status: 404 });
    return route.fulfill({ body: readFileSync(file), contentType: TYPES[path.extname(file)] ?? "text/html" });
  });
  await page.addInitScript(() => localStorage.setItem("ezo-mobile-prefs", JSON.stringify({ onboarded: true, apiUrl: "", language: "uz" })));
}

async function openStage(page: Page) {
  await page.goto("http://ezo-mobile.test/");
  await page.locator('nav button[data-go="chat"]').click();
  await page.locator("#mic").click();
  await expect(page.locator("#voiceStage")).toBeVisible();
  await expect(page.locator("#avatar")).toHaveAttribute("data-ezo-avatar", "webgl");
  await expect(page.locator("#avatar")).toHaveAttribute("data-state", "offline"); // no server: no pretending
}

test.beforeEach(() => {
  test.skip(!existsSync(path.join(MOBILE_DIST, "index.html")), "apps/mobile not built (pnpm -C apps/mobile build)");
});

test("mobile stage: the humanoid opens offline with no camera; the clap microphone is off until pressed; ten open/close cycles leak nothing", async ({ page }) => {
  await serveMobile(page);
  await openStage(page);
  await expect(page.locator("#cameraToggle")).toHaveCount(0);
  expect(await page.locator("video").count()).toBe(0);
  await expect(page.locator("#clapState")).toHaveAttribute("data-microphone", "off");
  await expect(page.locator("#clapToggle")).toBeEnabled();
  // Closing the stage frees the figure; reopening rebuilds it (ten times, one frame each time).
  for (let i = 0; i < 10; i++) {
    await page.locator("#stageClose").click();
    await expect(page.locator("#voiceStage")).toBeHidden();
    await page.locator("#mic").click();
    await expect(page.locator("#avatar")).toHaveAttribute("data-state", "offline");
    await expect(page.locator("#avatarBox svg")).toHaveCount(1);
    await expect(page.locator("#clapState")).toHaveAttribute("data-microphone", "off");
  }
});
