import { expect, test, type Page } from "@playwright/test";

// Camera attention on the voice stage. Every sensing input here is SIMULATED (an injected
// provider that invents frames); these tests prove the UI rules and the labelling, not a
// camera. Without a provider the control must be disabled and explain why.

async function installSimulatedSensing(page: Page) {
  await page.addInitScript(() => {
    const w = window as unknown as Record<string, unknown>;
    w.__sensing = [] as string[];
    w.ezoSensingProvider = {
      simulated: true,
      start: async (o: { onStatus: (s: unknown) => void; onHead: (f: unknown) => void; onHand?: (h: unknown) => void }) => {
        (w.__sensing as string[]).push("start");
        let phase = 0;
        o.onStatus({ camera: "tracking", faces: 1, hands: 0, since: performance.now(), simulated: true });
        const timer = setInterval(() => {
          phase += 0.1;
          const yaw = 0.5 * Math.sin(phase);
          o.onHead({ yaw, pitch: 0.1, roll: 0, gazeX: yaw, gazeY: 0.1, confidence: 1, timestamp: performance.now() });
        }, 50);
        w.__simulatedHand = (x: number, y: number) => o.onHand?.({ x, y, hand: "right", raised: true, confidence: 0.9, timestamp: performance.now() });
        return {
          stop: () => {
            clearInterval(timer);
            (w.__sensing as string[]).push("stop");
          },
        };
      },
    };
  });
}

test("camera: without a sensing engine the control is disabled and says why; the pointer is a labelled fallback", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("mode-voice").click();
  const row = page.getByTestId("camera-attention");
  await expect(row.getByTestId("camera-toggle")).toBeDisabled();
  await expect(row).toContainText("sensing dvigateli");
  await expect(row.getByTestId("camera-state")).toHaveAttribute("data-camera", "off");
  await page.getByTestId("voice-stage").getByTestId("ezo-humanoid").hover({ position: { x: 30, y: 30 } });
  await expect(row.getByTestId("attention")).toHaveText("EZO sichqonchaga qaraydi (kamera emas)");
});

test("camera: a simulated engine drives EZO's gaze, is labelled on screen, and stops when the tab hides or the stage closes", async ({ page }) => {
  await installSimulatedSensing(page);
  await page.goto("/");
  await page.getByTestId("mode-voice").click();
  const row = page.getByTestId("camera-attention");
  await expect(row.getByTestId("camera-toggle")).toBeEnabled();
  await row.getByTestId("camera-toggle").click();
  await expect(row.getByTestId("camera-state")).toHaveAttribute("data-camera", "tracking");
  await expect(row.getByTestId("camera-state")).toContainText("SIMULYATSIYA");
  await expect(row.getByTestId("attention")).toHaveText("EZO sizga qaraydi — SIMULYATSIYA — haqiqiy kamera emas");
  await page.evaluate(() => (window as unknown as { __simulatedHand: (x: number, y: number) => void }).__simulatedHand(-0.7, 0.3));
  await expect(row.getByTestId("attention")).toContainText("EZO qo‘lingizga qaraydi");
  await expect(row.getByTestId("camera-toggle")).toHaveText("Kamerani to‘xtatish");
  // The tab goes to the background: capture stops at once.
  await page.evaluate(() => {
    Object.defineProperty(document, "hidden", { configurable: true, get: () => true });
    document.dispatchEvent(new Event("visibilitychange"));
  });
  expect(await page.evaluate(() => (window as unknown as { __sensing: string[] }).__sensing)).toEqual(["start", "stop"]);
  await expect(row.getByTestId("camera-state")).toHaveAttribute("data-camera", "off");
  await page.evaluate(() => {
    Object.defineProperty(document, "hidden", { configurable: true, get: () => false });
    document.dispatchEvent(new Event("visibilitychange"));
  });
  await row.getByTestId("camera-toggle").click();
  await expect(row.getByTestId("camera-state")).toHaveAttribute("data-camera", "tracking");
  // Leaving the voice stage releases the figure and the camera with it.
  await page.getByTestId("mode-text").click();
  await expect(page.getByTestId("voice-stage")).toHaveCount(0);
  expect(await page.evaluate(() => (window as unknown as { __sensing: string[] }).__sensing)).toEqual(["start", "stop", "start", "stop"]);
});

test("voice stage: opened and closed ten times, the figure is rebuilt each time and nothing piles up", async ({ page }) => {
  await page.goto("/");
  const heap = () => page.evaluate(() => (performance as unknown as { memory?: { usedJSHeapSize: number } }).memory?.usedJSHeapSize ?? 0);
  await page.getByTestId("mode-voice").click();
  await expect(page.getByTestId("voice-stage").locator("canvas")).toHaveAttribute("data-ezo-avatar", "webgl");
  await page.getByTestId("mode-text").click();
  const before = await heap();
  for (let i = 0; i < 10; i++) {
    await page.getByTestId("mode-voice").click();
    await expect(page.getByTestId("voice-stage").locator("canvas")).toHaveAttribute("data-state", "idle");
    await expect(page.getByTestId("voice-frame").locator("svg")).toHaveCount(1);
    await page.getByTestId("mode-text").click();
    await expect(page.getByTestId("voice-stage")).toHaveCount(0);
  }
  expect(await page.locator("canvas[data-ezo-avatar]").count()).toBeLessThanOrEqual(1); // only the home figure
  const after = await heap();
  expect(after - before).toBeLessThan(40 * 1024 * 1024);
});
