import { expect, test, type Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { mkdirSync, copyFileSync } from "node:fs";
import path from "node:path";

// Energy renderer rules in Chromium: stills, bounded power, context recovery and state
// transitions. No camera, microphone or generated audio is simulated in this spec.

const ROOT = path.resolve(__dirname, "../../..");
const OUT = path.resolve(__dirname, "../.demo");
const esbuild = path.join(ROOT, "apps/desktop/node_modules/.bin/esbuild"); // the desktop app pins esbuild

test.beforeAll(() => {
  mkdirSync(OUT, { recursive: true });
  execFileSync(esbuild, [path.join(ROOT, "packages/avatar/demo/demo.ts"), "--bundle", "--format=iife", `--outfile=${path.join(OUT, "demo.js")}`, "--log-level=warning"]);
  copyFileSync(path.join(ROOT, "packages/avatar/demo/index.html"), path.join(OUT, "index.html"));
});

const open = (page: Page, query: string) => page.goto(`file://${path.join(OUT, "index.html")}?${query}`);
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
  await expect(canvas).toHaveAttribute("data-state", "speaking");

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

test("avatar: energy states and quality profiles keep a complete, finite composition", async ({ page }) => {
  await open(page, "state=idle&quality=high&reduced=1");
  const canvas = page.locator("#stage");
  for (const state of ["idle", "listening", "recognizing", "thinking", "working", "speaking", "success", "error", "offline"]) {
    await page.evaluate((s) => (window as unknown as { avatar: { setState(s: string): void } }).avatar.setState(s), state);
    await expect(canvas).toHaveAttribute("data-state", state === "success" ? /success|idle/ : state);
    await expect(canvas).toHaveAttribute("data-style", "energy");
  }
  const high = await page.evaluate(() => (window as unknown as { avatar: { getQuality(): { points: number } } }).avatar.getQuality().points);
  await page.evaluate(() => (window as unknown as { avatar: { setQuality(s: string): void } }).avatar.setQuality("low"));
  await expect(canvas).toHaveAttribute("data-quality", "low");
  const low = await page.evaluate(() => (window as unknown as { avatar: { getQuality(): { points: number } } }).avatar.getQuality().points);
  expect(low).toBeLessThan(high);
  expect(low).toBeGreaterThan(10_000);
});
