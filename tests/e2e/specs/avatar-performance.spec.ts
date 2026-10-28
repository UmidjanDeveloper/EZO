import { devices, expect, test, type Browser } from "@playwright/test";
import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";

// Measures EZO's humanoid on the real voice stage (its largest, heaviest view). CI renders WebGL with SwiftShader on the
// CPU, so the frame times here are a worst-case software path on a shared VM, not a phone or
// PC GPU. They are recorded, not asserted. The asserted budgets do not depend on hardware:
// point counts, the device-pixel-ratio cap, lower quality on dense phone screens, and a
// running draw loop.

interface Measurement {
  profile: string;
  quality: string;
  points: number;
  buildMs: number;
  css: { width: number; height: number };
  backing: { width: number; height: number };
  frames: number;
  fps: number;
  intervalMedianMs: number;
  intervalP95Ms: number;
  drawMedianMs: number;
  drawP95Ms: number;
  /** JS heap of the whole page after 4 s of animation (Chromium only; null elsewhere). */
  heapMB: number | null;
  /** Time from navigation start to the first avatar frame, as the browser measured it. */
  firstFrameMs: number | null;
}

const PROFILES = [
  { name: "desktop 1280x800 @1x", options: { viewport: { width: 1280, height: 800 }, deviceScaleFactor: 1 } },
  { name: "Pixel 7 412x839 @2.625x", options: { ...devices["Pixel 7"] } },
];

async function measure(browser: Browser, profile: (typeof PROFILES)[number]): Promise<Measurement> {
  const context = await browser.newContext(profile.options);
  const page = await context.newPage();
  await page.goto("/");
  await page.getByTestId("mode-voice").click();
  const canvas = page.getByTestId("voice-stage").getByTestId("ezo-humanoid").locator("canvas");
  await expect(canvas).toHaveAttribute("data-ezo-avatar", "webgl");
  await page.waitForTimeout(1000); // let the first frames and shader compilation settle
  const sample = await canvas.evaluate(async (el: HTMLCanvasElement) => {
    const gl = el.getContext("webgl") as WebGLRenderingContext;
    const intervals: number[] = [];
    const draws: number[] = [];
    let last = 0;
    const end = performance.now() + 4000;
    await new Promise<void>((resolve) => {
      const tick = (t: number) => {
        // The avatar's own rAF callback for this frame ran first; finish() waits for its GPU work.
        gl.finish();
        draws.push(performance.now() - t);
        if (last) intervals.push(t - last);
        last = t;
        if (performance.now() < end) requestAnimationFrame(tick);
        else resolve();
      };
      requestAnimationFrame(tick);
    });
    const rect = el.getBoundingClientRect();
    const memory = (performance as unknown as { memory?: { usedJSHeapSize: number } }).memory;
    const nav = performance.getEntriesByType("navigation")[0] as PerformanceNavigationTiming | undefined;
    return {
      intervals,
      draws,
      heapMB: memory ? Number((memory.usedJSHeapSize / 1048576).toFixed(1)) : null,
      firstFrameMs: nav ? Number((nav.domContentLoadedEventEnd + Number(el.dataset.buildMs ?? 0)).toFixed(0)) : null,
      quality: el.dataset.quality ?? "",
      points: Number(el.dataset.points),
      buildMs: Number(el.dataset.buildMs),
      css: { width: Math.round(rect.width), height: Math.round(rect.height) },
      backing: { width: el.width, height: el.height },
    };
  });
  await context.close();
  const pct = (values: number[], p: number) => {
    const sorted = [...values].sort((a, b) => a - b);
    return sorted.length ? Number(sorted[Math.min(sorted.length - 1, Math.floor(p * sorted.length))].toFixed(2)) : NaN;
  };
  const total = sample.intervals.reduce((a, b) => a + b, 0);
  return {
    profile: profile.name,
    quality: sample.quality,
    points: sample.points,
    buildMs: sample.buildMs,
    css: sample.css,
    backing: sample.backing,
    frames: sample.intervals.length + 1,
    fps: total ? Number(((sample.intervals.length * 1000) / total).toFixed(1)) : 0,
    intervalMedianMs: pct(sample.intervals, 0.5),
    intervalP95Ms: pct(sample.intervals, 0.95),
    drawMedianMs: pct(sample.draws, 0.5),
    drawP95Ms: pct(sample.draws, 0.95),
    heapMB: sample.heapMB,
    firstFrameMs: sample.firstFrameMs,
  };
}

test("avatar performance: hardware-independent budgets hold and frame times are recorded", async ({ browser }) => {
  test.setTimeout(90_000);
  const results: Measurement[] = [];
  for (const profile of PROFILES) results.push(await measure(browser, profile));

  const reports = path.resolve(__dirname, "../reports");
  mkdirSync(reports, { recursive: true });
  writeFileSync(path.join(reports, "avatar-performance.json"), JSON.stringify(results, null, 2));
  for (const r of results) {
    const line =
      `${r.profile}: quality=${r.quality} points=${r.points} build=${r.buildMs}ms ` +
      `canvas=${r.css.width}x${r.css.height} backing=${r.backing.width}x${r.backing.height} ` +
      `fps=${r.fps} interval p50/p95=${r.intervalMedianMs}/${r.intervalP95Ms}ms ` +
      `draw+finish p50/p95=${r.drawMedianMs}/${r.drawP95Ms}ms heap=${r.heapMB ?? "?"}MB first-frame≈${r.firstFrameMs ?? "?"}ms (SwiftShader, CI VM)`;
    console.log(process.env.GITHUB_ACTIONS ? `::notice title=Avatar performance::${line}` : line);
    test.info().annotations.push({ type: "avatar-performance", description: line });
  }

  const [desktop, phone] = results;
  // The draw loop runs (it pauses only when hidden or with reduced motion).
  for (const r of results) expect(r.frames).toBeGreaterThan(10);
  // The owner's PC has under 16 GB: the whole page, avatar included, must stay small.
  for (const r of results) if (r.heapMB !== null) expect(r.heapMB).toBeLessThan(200);
  // Point budgets (docs/devices/HUMANOID.md, 2026-10-28 bust: 45,038 high / 19,579 low
  // on the voice stage). They guard against regressions; raising them is a deliberate change.
  expect(desktop.quality).toBe("high");
  expect(desktop.points).toBeLessThanOrEqual(50_000);
  // Dense phone screens get the lighter figure, and the backing store is capped at 2x.
  expect(phone.quality).toBe("low");
  expect(phone.points).toBeLessThanOrEqual(20_000);
  for (const r of results) {
    expect(r.backing.width).toBeLessThanOrEqual(Math.ceil(r.css.width * 2) + 1);
    expect(r.backing.height).toBeLessThanOrEqual(Math.ceil(r.css.height * 2) + 1);
  }
});
