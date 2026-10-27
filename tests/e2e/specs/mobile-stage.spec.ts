import { expect, test, type Page } from "@playwright/test";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";

// The built Android web app (apps/mobile/dist) served from memory on a fake origin, as the
// WebView loads it, without a server: the voice stage must open, show the humanoid, and the
// camera control must be enabled only when the bundled, verified vision assets are served —
// otherwise disabled with the honest reason. Touch/pointer is a labelled fallback. The engine
// itself runs in perception.spec.ts (project "perception", SIMULATED camera). Nothing here is
// a phone or a camera.

const MOBILE_DIST = path.resolve(__dirname, "../../../apps/mobile/dist");
const TYPES: Record<string, string> = { ".js": "text/javascript", ".css": "text/css", ".json": "application/json", ".wasm": "application/wasm", ".task": "application/octet-stream", ".txt": "text/plain" };

async function serveMobile(page: Page, vision: "bundled" | "missing" | "tampered" = "bundled") {
  await page.route("http://ezo-mobile.test/**", (route) => {
    const pathname = new URL(route.request().url()).pathname.replace(/^\/$/, "/index.html");
    if (pathname.startsWith("/vision/") && vision === "missing") return route.fulfill({ status: 404 });
    const file = path.join(MOBILE_DIST, pathname);
    if (!existsSync(file)) return route.fulfill({ status: 404 });
    if (pathname === "/vision/vision-assets.json" && vision === "tampered") return route.fulfill({ body: '{"face":{"url":"/vision/face_landmarker.task"}}', contentType: "application/json" });
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

test("mobile stage: the humanoid opens offline, the camera control is enabled by the verified bundle, touch is a labelled fallback", async ({ page }) => {
  test.skip(!existsSync(path.join(MOBILE_DIST, "vision/vision-assets.json")), "apps/mobile built without vision assets");
  await serveMobile(page);
  await openStage(page);
  await expect(page.locator("#cameraToggle")).toBeEnabled();
  await expect(page.locator("#cameraPrivacy")).toContainText("MediaPipe");
  await expect(page.locator("#cameraState")).toHaveAttribute("data-camera", "off"); // never on by itself
  await expect(page.locator("#clapState")).toHaveAttribute("data-microphone", "off");
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
    await expect(page.locator("#cameraState")).toHaveAttribute("data-camera", "off");
  }
});

test("mobile stage: without the bundled assets the camera control is disabled and says why; a tampered manifest is refused", async ({ page }) => {
  await serveMobile(page, "missing");
  await openStage(page);
  await expect(page.locator("#cameraToggle")).toBeDisabled();
  await expect(page.locator("#cameraPrivacy")).toContainText("vision assets yo‘q");
  await page.mouse.move(80, 300);
  await page.mouse.move(120, 320);
  await expect(page.locator("#attention")).toContainText("(kamera emas)"); // the fallback does not need the engine

  await page.unrouteAll();
  await serveMobile(page, "tampered");
  await openStage(page);
  await expect(page.locator("#cameraToggle")).toBeDisabled();
  await expect(page.locator("#cameraPrivacy")).toContainText("tekshiruvdan o‘tmadi");
});
