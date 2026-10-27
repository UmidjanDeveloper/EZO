import { expect, test, type Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, copyFileSync } from "node:fs";
import path from "node:path";

// The figure's modes, on the real demo page (packages/avatar/demo) in Chromium: reduced
// motion draws stills, low power caps the loop, a lost WebGL context is recovered, and every
// one of the nine states reaches the face. No camera, no device: these are renderer rules.

const ROOT = path.resolve(__dirname, "../../..");
const OUT = path.resolve(__dirname, "../.demo");
const esbuild = path.join(ROOT, "apps/desktop/node_modules/.bin/esbuild"); // the desktop app pins esbuild

test.beforeAll(() => {
  mkdirSync(OUT, { recursive: true });
  if (!existsSync(path.join(OUT, "demo.js"))) {
    execFileSync(esbuild, [path.join(ROOT, "packages/avatar/demo/demo.ts"), "--bundle", "--format=iife", `--outfile=${path.join(OUT, "demo.js")}`, "--log-level=warning"]);
  }
  copyFileSync(path.join(ROOT, "packages/avatar/demo/index.html"), path.join(OUT, "index.html"));
});

const open = (page: Page, query: string) => page.goto(`file://${path.join(OUT, "index.html")}?${query}`);
const face = (page: Page) => page.evaluate(() => (window as unknown as { avatar: { getFace(): Record<string, unknown> } }).avatar.getFace());
const frames = (page: Page) => page.evaluate(() => (window as unknown as { avatar: { getFrameCount(): number } }).avatar.getFrameCount());

test("avatar: reduced motion draws a still (no loop), low power caps the loop, full motion runs", async ({ page }) => {
  await open(page, "state=speaking&reduced=1");
  const canvas = page.locator("#stage");
  await expect(canvas).toHaveAttribute("data-motion", "reduced");
  await page.waitForTimeout(600);
  const still = await frames(page);
  await page.waitForTimeout(600);
  expect(await frames(page)).toBe(still); // nothing animates
  expect(still).toBeGreaterThan(0); // but the figure was drawn
  expect((await face(page)).mouth).toBeGreaterThan(0); // a speaking still shows an open mouth

  await open(page, "state=idle&power=low");
  await expect(canvas).toHaveAttribute("data-power", "low");
  await page.waitForTimeout(1200);
  const low = await frames(page);
  await open(page, "state=idle&power=high");
  await expect(canvas).toHaveAttribute("data-power", "high");
  await page.waitForTimeout(1200);
  const high = await frames(page);
  expect(low).toBeGreaterThan(5);
  expect(low).toBeLessThan(high); // the economy mode really draws less
});

test("avatar: a lost WebGL context is recovered and drawing resumes", async ({ page }) => {
  await open(page, "state=idle");
  const canvas = page.locator("#stage");
  await expect(canvas).toHaveAttribute("data-ezo-avatar", "webgl");
  await page.waitForTimeout(400);
  const before = await frames(page);
  expect(before).toBeGreaterThan(3);
  const lost = await page.evaluate(() => {
    const gl = (document.getElementById("stage") as HTMLCanvasElement).getContext("webgl");
    const ext = gl?.getExtension("WEBGL_lose_context");
    if (!ext) return false;
    ext.loseContext();
    setTimeout(() => ext.restoreContext(), 300);
    return true;
  });
  test.skip(!lost, "WEBGL_lose_context not available in this Chromium");
  await page.waitForTimeout(200);
  const during = await frames(page);
  await page.waitForTimeout(1200);
  const after = await frames(page);
  expect(after).toBeGreaterThan(during + 3); // the loop restarted after restore
});

test("avatar: all nine states reach the face (lids, brows, mouth, corners) and the canvas says which", async ({ page }) => {
  await open(page, "state=idle");
  const faces: Record<string, Record<string, unknown>> = {};
  for (const state of ["idle", "listening", "recognizing", "thinking", "working", "speaking", "success", "error", "offline"]) {
    await page.evaluate((s) => (window as unknown as { avatar: { setState(s: string): void } }).avatar.setState(s), state);
    // A live level, fed every 50 ms like a real meter would (a single value goes stale after 0.4 s).
    await page.evaluate(
      () =>
        new Promise<void>((resolve) => {
          const avatar = (window as unknown as { avatar: { setLevel(l: number): void } }).avatar;
          const timer = setInterval(() => avatar.setLevel(0.7), 50);
          setTimeout(() => {
            clearInterval(timer);
            resolve();
          }, 600);
        }),
    );
    await expect(page.locator("#stage")).toHaveAttribute("data-state", state === "success" ? /success|idle/ : state);
    faces[state] = await face(page);
  }
  expect(faces.speaking!.mouth as number).toBeGreaterThan(0.3); // the measured level opens the jaw
  expect(faces.listening!.mouth as number).toBe(0); // the microphone never opens EZO's mouth
  expect(faces.listening!.brow as number).toBeGreaterThan(0);
  expect(faces.thinking!.brow as number).toBeLessThan(0);
  expect(faces.offline!.droop as number).toBeGreaterThan(0.3);
  expect(faces.error!.smile as number).toBeLessThan(0);
  expect(faces.idle!.droop as number).toBeLessThan(0.05);
});
