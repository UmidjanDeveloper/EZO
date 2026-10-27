import { expect, test, type Page } from "@playwright/test";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";

// The built Android web app (apps/mobile/dist) served from memory on a fake origin, as the
// WebView loads it, without a server: the voice stage must open, show the humanoid, the
// camera control must be disabled with its reason (no sensing engine in this build), and a
// SIMULATED provider must be labelled as such. Nothing here is a phone or a camera.

const MOBILE_DIST = path.resolve(__dirname, "../../../apps/mobile/dist");

async function serveMobile(page: Page) {
  await page.route("http://ezo-mobile.test/**", (route) => {
    const file = path.join(MOBILE_DIST, new URL(route.request().url()).pathname.replace(/^\/$/, "/index.html"));
    if (!existsSync(file)) return route.fulfill({ status: 404 });
    const type = file.endsWith(".js") ? "text/javascript" : file.endsWith(".css") ? "text/css" : "text/html";
    return route.fulfill({ body: readFileSync(file), contentType: type });
  });
  await page.addInitScript(() => localStorage.setItem("ezo-mobile-prefs", JSON.stringify({ onboarded: true, apiUrl: "", language: "uz" })));
}

test.beforeEach(() => {
  test.skip(!existsSync(path.join(MOBILE_DIST, "index.html")), "apps/mobile not built (pnpm -C apps/mobile build)");
});

test("mobile stage: the humanoid opens offline, the camera control is disabled and says why, touch is a labelled fallback", async ({ page }) => {
  await serveMobile(page);
  await page.goto("http://ezo-mobile.test/");
  await page.locator('nav button[data-go="chat"]').click();
  await page.locator("#mic").click();
  await expect(page.locator("#voiceStage")).toBeVisible();
  await expect(page.locator("#avatar")).toHaveAttribute("data-ezo-avatar", "webgl");
  await expect(page.locator("#avatar")).toHaveAttribute("data-state", "offline"); // no server: no pretending
  await expect(page.locator("#cameraToggle")).toBeDisabled();
  await expect(page.locator("#cameraPrivacy")).toContainText("sensing dvigateli");
  await page.mouse.move(80, 300); // over the figure, away from the overlaid controls
  await page.mouse.move(120, 320);
  await expect(page.locator("#attention")).toContainText("(kamera emas)");
  // Closing the stage frees the figure; reopening rebuilds it (ten times, one frame each time).
  for (let i = 0; i < 10; i++) {
    await page.locator("#stageClose").click();
    await expect(page.locator("#voiceStage")).toBeHidden();
    await page.locator("#mic").click();
    await expect(page.locator("#avatar")).toHaveAttribute("data-state", "offline");
    await expect(page.locator("#avatarBox svg")).toHaveCount(1);
  }
});

test("mobile stage: a simulated engine is labelled, drives the gaze, and stops with the stage or in the background", async ({ page }) => {
  await serveMobile(page);
  await page.addInitScript(() => {
    const w = window as unknown as Record<string, unknown>;
    w.__sensing = [] as string[];
    w.ezoSensingProvider = {
      simulated: true,
      start: async (o: { onStatus: (s: unknown) => void; onHead: (f: unknown) => void }) => {
        (w.__sensing as string[]).push("start");
        o.onStatus({ camera: "tracking", faces: 1, hands: 0, since: performance.now(), simulated: true });
        const timer = setInterval(() => o.onHead({ yaw: 0.3, pitch: 0, roll: 0, gazeX: 0.3, gazeY: 0, confidence: 1, timestamp: performance.now() }), 50);
        return { stop: () => { clearInterval(timer); (w.__sensing as string[]).push("stop"); } };
      },
    };
  });
  await page.goto("http://ezo-mobile.test/");
  await page.locator('nav button[data-go="chat"]').click();
  await page.locator("#mic").click();
  await expect(page.locator("#cameraToggle")).toBeEnabled();
  await page.locator("#cameraToggle").click();
  await expect(page.locator("#cameraState")).toHaveAttribute("data-camera", "tracking");
  await expect(page.locator("#cameraState")).toContainText("SIMULYATSIYA");
  await expect(page.locator("#attention")).toHaveText("EZO sizga qaraydi — SIMULYATSIYA — haqiqiy kamera emas");
  await page.evaluate(() => {
    Object.defineProperty(document, "hidden", { configurable: true, get: () => true });
    document.dispatchEvent(new Event("visibilitychange"));
  });
  await expect(page.locator("#cameraState")).toHaveAttribute("data-camera", "off");
  await page.evaluate(() => {
    Object.defineProperty(document, "hidden", { configurable: true, get: () => false });
    document.dispatchEvent(new Event("visibilitychange"));
  });
  await page.locator("#cameraToggle").click();
  await expect(page.locator("#cameraState")).toHaveAttribute("data-camera", "tracking");
  await page.locator("#stageClose").click();
  expect(await page.evaluate(() => (window as unknown as { __sensing: string[] }).__sensing)).toEqual(["start", "stop", "start", "stop"]);
});
