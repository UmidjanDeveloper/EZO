import { expect, test } from "@playwright/test";

test("EZO presence: the humanoid face greets on the home screen", async ({ page }) => {
  await page.goto("/");
  const face = page.locator("main").getByTestId("ezo-humanoid");
  await expect(face).toHaveAttribute("data-state", "idle");
  await expect(face.locator("canvas")).toHaveAttribute("data-ezo-avatar", "webgl");
  await expect(page.getByTestId("ezo-status")).toHaveCount(0); // nothing to report while idle
});

test("EZO presence: header status shows the reply finishing, then settles to idle", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("composer-input").fill("Salom!");
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("message-assistant")).toContainText("oflayn rejimda");

  const status = page.getByTestId("ezo-status");
  await expect(status).toHaveAttribute("data-state", "completed");
  await expect(status).toHaveText("Tayyor");
  await expect(status).toHaveCount(0, { timeout: 5_000 }); // back to idle
});

test("EZO presence: voice stage shows the humanoid, idle", async ({ page }) => {
  await page.route("**/api/status", (route) => route.fulfill({ json: { offline_mode: false } }));
  await page.goto("/");
  await page.getByTestId("mode-voice").click();
  const face = page.getByTestId("voice-stage").getByTestId("ezo-humanoid");
  await expect(face).toHaveAttribute("data-state", "idle");
  await expect(face.locator("canvas")).toHaveAttribute("data-ezo-avatar", "webgl");
  await expect(face.locator("canvas")).toHaveAttribute("data-state", "idle");
});

test("EZO presence: camera is opt-in, local, and released on stop/unmount", async ({ page }) => {
  // A simulated video-only stream: this proves consent/cleanup wiring, not a physical camera.
  await page.addInitScript(() => {
    const w = window as unknown as { __cameraRequests: number; __cameraStops: number; __cameraAudio: number };
    w.__cameraRequests = 0; w.__cameraStops = 0; w.__cameraAudio = 0;
    navigator.mediaDevices.getUserMedia = async (constraints) => {
      w.__cameraRequests += 1;
      if (constraints?.audio) w.__cameraAudio += 1;
      const canvas = document.createElement("canvas"); canvas.width = 320; canvas.height = 240;
      const ctx = canvas.getContext("2d")!; ctx.fillStyle = "#202020"; ctx.fillRect(0, 0, 320, 240);
      const stream = canvas.captureStream(15);
      for (const track of stream.getTracks()) {
        const stop = track.stop.bind(track);
        track.stop = () => { w.__cameraStops += 1; stop(); };
      }
      return stream;
    };
  });
  await page.goto("/");
  await page.getByTestId("mode-voice").click();
  await expect(page.getByTestId("camera-toggle")).not.toBeVisible();
  expect(await page.evaluate(() => (window as unknown as { __cameraRequests: number }).__cameraRequests)).toBe(0);
  await page.getByTestId("voice-settings").locator(":scope > summary").click();
  await page.getByTestId("camera-toggle").click();
  await expect(page.getByTestId("camera-status")).toHaveAttribute("data-status", /searching|tracking/, { timeout: 30_000 });
  expect(await page.evaluate(() => (window as unknown as { __cameraAudio: number }).__cameraAudio)).toBe(0);
  await page.getByTestId("camera-toggle").click();
  await expect(page.getByTestId("camera-status")).toHaveAttribute("data-status", "off");
  expect(await page.evaluate(() => (window as unknown as { __cameraStops: number }).__cameraStops)).toBeGreaterThan(0);
  // Re-enable, then close the stage: unmount must stop the track too.
  await page.getByTestId("camera-toggle").click();
  await expect(page.getByTestId("camera-status")).toHaveAttribute("data-status", /searching|tracking/, { timeout: 30_000 });
  const before = await page.evaluate(() => (window as unknown as { __cameraStops: number }).__cameraStops);
  await page.getByTestId("mode-text").click();
  await expect(page.getByTestId("voice-stage")).toHaveCount(0);
  expect(await page.evaluate(() => (window as unknown as { __cameraStops: number }).__cameraStops)).toBeGreaterThan(before);
});

test("EZO presence: denied camera permission is reported and leaves no active camera", async ({ page }) => {
  await page.addInitScript(() => {
    navigator.mediaDevices.getUserMedia = async () => { throw new DOMException("denied", "NotAllowedError"); };
  });
  await page.goto("/");
  await page.getByTestId("mode-voice").click();
  await page.getByTestId("voice-settings").locator(":scope > summary").click();
  await page.getByTestId("camera-toggle").click();
  await expect(page.getByTestId("camera-status")).toHaveAttribute("data-status", "error");
  await expect(page.getByTestId("presence-controls").getByRole("alert")).toContainText("Kamera ruxsati berilmadi");
  await expect(page.getByTestId("camera-toggle")).toHaveAttribute("aria-pressed", "false");
});
