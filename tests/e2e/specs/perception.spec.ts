import { expect, test, type Page } from "@playwright/test";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";

// The REAL perception engine (@ezo/face-tracking: MediaPipe in a worker, assets served from
// this origin and SHA256-verified) on the voice stage, driven by Chromium's FAKE camera and a
// FAKE microphone file with clap-like bursts (playwright.config.ts, project "perception").
// This is a SIMULATION: it proves the wiring, the honesty of the states and the cleanup. It
// does not prove that a real face, hand or clap is recognised — only the owner can.

const SILENT_WAV = (() => {
  const rate = 8000;
  const samples = rate * 2;
  const buffer = Buffer.alloc(44 + samples * 2);
  buffer.write("RIFF", 0);
  buffer.writeUInt32LE(36 + samples * 2, 4);
  buffer.write("WAVEfmt ", 8);
  buffer.writeUInt32LE(16, 16);
  buffer.writeUInt16LE(1, 20);
  buffer.writeUInt16LE(1, 22);
  buffer.writeUInt32LE(rate, 24);
  buffer.writeUInt32LE(rate * 2, 28);
  buffer.writeUInt16LE(2, 32);
  buffer.writeUInt16LE(16, 34);
  buffer.write("data", 36);
  buffer.writeUInt32LE(samples * 2, 40);
  for (let i = 0; i < samples; i++) buffer.writeInt16LE(Math.round(Math.sin(i / 20) * 8000), 44 + i * 2);
  return buffer;
})();

test.setTimeout(120_000);

// Screenshots for docs/devices/img when EZO_SHOTS_DIR is set (CI never sets it). They show the
// SIMULATED camera (Chromium's synthetic picture) and are labelled so in the file name.
const SHOTS = process.env.EZO_SHOTS_DIR;
const shot = async (page: Page, name: string) => {
  if (SHOTS) await page.screenshot({ path: path.join(SHOTS, `section-c-simulation-${name}.png`), fullPage: false });
};
// MediaPipe prints its TensorFlow Lite "INFO" line on stderr/console.error; it is not an error.
const realErrors = (errors: string[]) => errors.filter((e) => !/favicon|^INFO: Created TensorFlow Lite XNNPACK delegate/.test(e));

test("perception (simulated camera): assets verify, the worker runs inference, the status is honest, three open/close cycles leak nothing", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => message.type() === "error" && errors.push(message.text()));
  await page.goto("/");
  await page.getByTestId("mode-voice").click();
  await page.getByTestId("voice-settings").locator(":scope > summary").click();
  const row = page.getByTestId("camera-attention");
  await expect(row.getByTestId("camera-toggle")).toBeEnabled({ timeout: 20_000 }); // vision-assets.json validated
  await expect(row).toContainText("MediaPipe");
  for (let cycle = 0; cycle < 3; cycle++) {
    await row.getByTestId("camera-toggle").click();
    // Fake camera: the worker loads the pinned WASM + models (SHA256) and runs; no face is in
    // the synthetic picture, so the honest state is "lost" (or "tracking" if the fake frame fools it).
    await expect(row.getByTestId("camera-state")).toHaveAttribute("data-camera", /tracking|lost/, { timeout: 60_000 });
    await expect(row.getByTestId("camera-indicator")).toContainText("Camera active");
    await expect.poll(async () => Number(await row.getAttribute("data-fps")), { timeout: 30_000 }).toBeGreaterThan(0);
    expect(Number(await row.getAttribute("data-inference-ms"))).toBeGreaterThan(0);
    if (cycle === 0) {
      await shot(page, "web-stage");
      // The owner's Diagnostics: plain text, numbers and words only, never an image or landmarks.
      await row.getByTestId("diagnostics").locator("summary").click();
      await row.getByTestId("diagnostics-copy").click();
      const text = (await row.getByTestId("diagnostics-text").textContent()) ?? "";
      expect(text).toMatch(/^EZO web diagnostics/);
      expect(text).toMatch(/camera: (tracking|lost)/);
      expect(text).toMatch(/figure\.fps: \d/);
      expect(text).toMatch(/vision: assets verified/);
      expect(text).not.toMatch(/data:image|landmark|base64/);
    }
    await row.getByTestId("camera-toggle").click();
    await expect(row.getByTestId("camera-state")).toHaveAttribute("data-camera", "off");
    await expect(row.getByTestId("camera-indicator")).toContainText("Camera off");
    expect(await page.evaluate(() => (document.querySelector("video") as HTMLVideoElement).srcObject)).toBeNull();
  }
  expect(realErrors(errors)).toEqual([]);
});

test("perception (simulated camera): a hidden tab stops the camera at once; leaving the stage releases everything", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("mode-voice").click();
  await page.getByTestId("voice-settings").locator(":scope > summary").click();
  const row = page.getByTestId("camera-attention");
  await expect(row.getByTestId("camera-toggle")).toBeEnabled({ timeout: 20_000 });
  await row.getByTestId("camera-toggle").click();
  await expect(row.getByTestId("camera-state")).toHaveAttribute("data-camera", /tracking|lost/, { timeout: 60_000 });
  await page.evaluate(() => {
    Object.defineProperty(document, "hidden", { configurable: true, get: () => true });
    document.dispatchEvent(new Event("visibilitychange"));
  });
  await expect(row.getByTestId("camera-state")).toHaveAttribute("data-camera", "off");
  await page.evaluate(() => {
    Object.defineProperty(document, "hidden", { configurable: true, get: () => false });
    document.dispatchEvent(new Event("visibilitychange"));
  });
  await expect(row.getByTestId("camera-state")).toHaveAttribute("data-camera", "off"); // never restarts by itself
  await page.getByTestId("mode-text").click();
  await expect(page.getByTestId("voice-stage")).toHaveCount(0);
  expect(await page.evaluate(() => document.querySelectorAll("video").length)).toBe(0);
});

test("clap (simulated microphone file): separate consent, a clap is heard, EZO answers with the real TTS route and speaks; no provider = honest notice", async ({ page }) => {
  let synthesized = 0;
  await page.route("**/api/voice/status", (route) =>
    route.fulfill({ json: { speech_to_text: [], text_to_speech: ["fixture-tts"], realtime: false, max_audio_mb: 10, stores_audio: false, browser_fallback: true } }),
  );
  await page.route("**/api/voice/speak", async (route) => {
    synthesized += 1;
    const body = route.request().postDataJSON() as { text: string; language: string };
    expect(body).toEqual({ text: "Eshitaman seni.", language: "uz" });
    await route.fulfill({ body: SILENT_WAV, contentType: "audio/wav", headers: { "X-EZO-Voice-Provider": "fixture-tts", "Access-Control-Expose-Headers": "X-EZO-Voice-Provider" } });
  });
  await page.goto("/");
  await page.getByTestId("mode-voice").click();
  await page.getByTestId("voice-settings").locator(":scope > summary").click();
  const row = page.getByTestId("camera-attention");
  await expect(row.getByTestId("clap-toggle")).toBeEnabled({ timeout: 20_000 });
  await expect(row.getByTestId("clap-state")).toHaveAttribute("data-microphone", "off"); // off until the owner presses
  await row.getByTestId("clap-toggle").click();
  await expect(row.getByTestId("clap-state")).toHaveAttribute("data-microphone", "active", { timeout: 20_000 });
  await expect(row.getByTestId("microphone-indicator")).toContainText("Microphone active");
  await expect(row.getByTestId("clap-heard")).toContainText("Qarsak eshitildi", { timeout: 30_000 });
  // The acknowledgement: real TTS route (mocked here), real playback, the stage shows "speaking".
  await expect.poll(() => synthesized, { timeout: 15_000 }).toBe(1);
  await expect(page.getByTestId("voice-stage").getByTestId("ezo-humanoid")).toHaveAttribute("data-state", "speaking", { timeout: 10_000 });
  await expect(row).toHaveAttribute("data-tts-provider", "fixture-tts");
  await expect(page.getByTestId("voice-stage").getByTestId("ezo-humanoid")).toHaveAttribute("data-state", "idle", { timeout: 15_000 });
  // The next clap answers from the cache: no second synthesis.
  await expect.poll(async () => Number(await row.getAttribute("data-clap-count")), { timeout: 30_000 }).toBeGreaterThanOrEqual(2);
  await expect(page.getByTestId("voice-stage").getByTestId("ezo-humanoid")).toHaveAttribute("data-state", "speaking", { timeout: 10_000 });
  expect(synthesized).toBe(1);
  await row.getByTestId("clap-toggle").click();
  await expect(row.getByTestId("clap-state")).toHaveAttribute("data-microphone", "off");
});

test("clap (simulated microphone file): without a voice provider the reply is not pretended", async ({ page }) => {
  await page.route("**/api/voice/speak", (route) => route.fulfill({ status: 503, json: { error: { code: "voice_not_configured", message: "no provider" } } }));
  await page.goto("/");
  await page.getByTestId("mode-voice").click();
  await page.getByTestId("voice-settings").locator(":scope > summary").click();
  const row = page.getByTestId("camera-attention");
  await expect(row.getByTestId("clap-toggle")).toBeEnabled({ timeout: 20_000 });
  await row.getByTestId("clap-toggle").click();
  await expect(row.getByTestId("clap-heard")).toContainText("Qarsak eshitildi", { timeout: 30_000 });
  await expect(page.getByRole("status").filter({ hasText: /Ovoz provayderi yo‘q|aytilmadi/ })).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId("voice-stage").getByTestId("ezo-humanoid")).not.toHaveAttribute("data-state", "speaking");
});

// ---- The Windows pill renderer (apps/desktop/dist, served from memory on a fake origin as the
// app's https://ezo.desktop protocol handler does) and the Android web app (apps/mobile/dist),
// both on the same real engine with the same fake camera. SIMULATION, not a PC or a phone.


const DESKTOP_DIST = path.resolve(__dirname, "../../../apps/desktop/dist");
const MOBILE_DIST = path.resolve(__dirname, "../../../apps/mobile/dist");

async function serveFromMemory(page: Page, origin: string, root: string) {
  await page.route(`${origin}/**`, (route) => {
    const file = path.join(root, decodeURIComponent(new URL(route.request().url()).pathname).replace(/^\/$/, "/index.html"));
    if (!existsSync(file)) return route.fulfill({ status: 404 });
    const ext = path.extname(file);
    const type = ext === ".js" ? "text/javascript" : ext === ".css" ? "text/css" : ext === ".json" ? "application/json" : ext === ".wasm" ? "application/wasm" : ext === ".html" ? "text/html" : "application/octet-stream";
    const headers: Record<string, string> = {};
    if (file.endsWith("vision.worker.js")) headers["Content-Security-Policy"] = "default-src 'none'; script-src 'self' blob: 'wasm-unsafe-eval'; connect-src 'self' blob:";
    return route.fulfill({ body: readFileSync(file), contentType: type, headers });
  });
}

const PILL_STRINGS = {
  idle: "EZO", idleHint: "{shortcut} — gapiring", expand: "Kattalashtirish", collapse: "Kichraytirish", cameraOff: "Kamera o‘chiq", cameraOn: "Kamerani yoqish", cameraStop: "Kamerani to‘xtatish",
  cameraRequesting: "Kamera so‘ralmoqda…", cameraTracking: "Kamera: yuz ko‘rinmoqda", cameraLost: "Kamera: yuz topilmadi", cameraPrivacy: "Tasvir kompyuteringizdan chiqmaydi.", cameraEngine: "Yuz/qo‘l kuzatuvi: MediaPipe.",
  cameraActive: "Kamera faol", cameraSettings: "Kamera sozlamalarda o‘chirilgan", cameraError: "Kamera xatosi: {detail}", attentionPointer: "EZO sichqonchaga qaraydi (kamera emas)", attentionHead: "EZO sizga qaraydi", attentionHand: "EZO qo‘lingizga qaraydi",
  clapListen: "Qarsakni tinglash", clapStop: "Tinglashni to‘xtatish", clapOff: "Qarsak mikrofoni o‘chiq", clapRequesting: "Mikrofon so‘ralmoqda…", clapActive: "Mikrofon (qarsak) faol", clapPrivacy: "Faqat qarsak.", clapSettings: "Qarsakni tinglash sozlamalarda o‘chiq", clapUnavailable: "Ovoz provayderi yo‘q — javob aytilmadi.",
  clap: "Qarsak eshitildi", micActive: "Mikrofon faol", speaking: "Gapiryapman…", speakingHint: "■", talk: "Gapirish", type: "Yozish", stop: "To‘xtatish", settings: "Sozlamalar", typePlaceholder: "…", history: "Tarix", newConversation: "Yangi", showHideHint: "Ctrl+Alt+H",
};

test("Windows pill (simulated camera): the stage on the real engine — assets verified, camera runs, clap heard, acknowledgement spoken through the main process, everything released on collapse", async ({ page }) => {
  test.skip(!existsSync(path.join(DESKTOP_DIST, "vision/vision-assets.json")), "apps/desktop not built with vision assets");
  await serveFromMemory(page, "https://ezo-desktop.test", DESKTOP_DIST);
  await page.addInitScript((strings) => {
    const listeners: Record<string, ((p: unknown) => void)[]> = {};
    const on = (c: string) => (cb: (p: unknown) => void) => (listeners[c] ??= []).push(cb);
    const w = window as unknown as Record<string, unknown>;
    w.__calls = [] as string[];
    w.__diag = [] as unknown[];
    const wav = (() => {
      const rate = 8000, n = rate;
      const b = new Uint8Array(44 + n * 2);
      const v = new DataView(b.buffer);
      const str = (o: number, s: string) => [...s].forEach((c, i) => (b[o + i] = c.charCodeAt(0)));
      str(0, "RIFF"); v.setUint32(4, 36 + n * 2, true); str(8, "WAVEfmt "); v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true);
      v.setUint32(24, rate, true); v.setUint32(28, rate * 2, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true); str(36, "data"); v.setUint32(40, n * 2, true);
      for (let i = 0; i < n; i++) v.setInt16(44 + i * 2, Math.round(Math.sin(i / 20) * 8000), true);
      return b;
    })();
    w.ezo = {
      init: async () => ({ strings, shortcut: "Ctrl+Alt+Space", language: "uz", status: { online: true, ai: true, voice: true, text: "ready" }, media: { microphone: true, camera: true }, lowPower: true, voiceVolume: 1, clap: { listening: true, startsListening: false }, build: { version: "test", sha: "test" } }),
      sendText: async () => ({}), sendAudio: async () => ({}), cancelTurn() {}, openSettings() {}, setFocusable() {}, setHeight() {},
      setExpanded: (v: boolean) => (listeners.expanded ?? []).forEach((cb) => cb(v)),
      refreshStatus: async () => ({ online: true, ai: true, voice: true, text: "ready" }), recentHistory: async () => ({ ok: true, messages: [] }), conversations: async () => ({ ok: true, conversations: [] }),
      switchConversation: async () => null, tasks: async () => [], cancelTask: async () => ({ ok: true }),
      speak: async (text: string, language: string) => {
        (w.__calls as string[]).push(`speak:${language}:${text}`);
        return { mimeType: "audio/wav", data: wav, provider: "fixture-tts" };
      },
      reportDiagnostics: (d: unknown) => (w.__diag as unknown[]).push(d),
      onToggle: on("toggle"), onNotice: on("notice"), onError: on("error"), onStage: on("stage"), onStatus: on("status"), onTasks: on("tasks"), onInit: on("init"), onVisibility: on("visibility"), onExpanded: on("expanded"),
    };
    w.__emit = (c: string, p: unknown) => (listeners[c] ?? []).forEach((cb) => cb(p));
  }, PILL_STRINGS);
  await page.goto("https://ezo-desktop.test/pill.html");
  await page.locator("#expand").click();
  await expect(page.locator("#cameraToggle")).toBeEnabled({ timeout: 20_000 });
  await expect(page.locator("#cameraPrivacy")).toContainText("MediaPipe");
  await page.locator("#cameraToggle").click();
  await expect(page.locator("#cameraState")).toHaveAttribute("data-camera", /tracking|lost/, { timeout: 60_000 });
  await expect(page.locator("#media span.cam")).toHaveText("CAM");
  await expect.poll(async () => Number(await page.locator("#stage").getAttribute("data-fps")), { timeout: 30_000 }).toBeGreaterThan(0);
  // Clap: separate consent (settings on) + the Listen button; the fake microphone file claps.
  await expect(page.locator("#clapToggle")).toBeEnabled();
  await page.locator("#clapToggle").click();
  await expect(page.locator("#clapState")).toHaveAttribute("data-microphone", "active", { timeout: 20_000 });
  await expect(page.locator("#clapHeard")).toContainText("Qarsak eshitildi", { timeout: 30_000 });
  await shot(page, "windows-pill-stage");
  await expect.poll(async () => (await page.evaluate(() => (window as unknown as { __calls: string[] }).__calls)).filter((c) => c.startsWith("speak:")), { timeout: 15_000 }).toEqual(["speak:uz:Eshitaman seni."]);
  await expect(page.locator("#pill")).toHaveClass(/speaking/, { timeout: 10_000 });
  await expect(page.locator("#pill")).toHaveClass(/idle/, { timeout: 15_000 });
  // Diagnostics reached the main process: numbers only.
  const diag = (await page.evaluate(() => (window as unknown as { __diag: Record<string, unknown>[] }).__diag)).at(-1)!;
  expect(diag).toMatchObject({ camera: expect.stringMatching(/tracking|lost/), microphone: "active", stage: "expanded", vision: "assets verified" });
  expect(JSON.stringify(diag)).not.toMatch(/landmark|base64|data:image/);
  // Collapse: camera, microphone and worker released.
  await page.locator("#expand").click();
  await expect(page.locator("#stage")).toBeHidden();
  await page.locator("#expand").click();
  await expect(page.locator("#cameraState")).toHaveAttribute("data-camera", "off");
  await expect(page.locator("#clapState")).toHaveAttribute("data-microphone", "off");
  await expect(page.locator("#media")).toBeEmpty();
});

test("Android web app (simulated camera): the stage on the real engine — camera runs and is released with the stage; clap consent is off by default", async ({ page }) => {
  test.skip(!existsSync(path.join(MOBILE_DIST, "vision/vision-assets.json")), "apps/mobile not built with vision assets");
  await serveFromMemory(page, "https://ezo-mobile.test", MOBILE_DIST);
  await page.addInitScript(() => localStorage.setItem("ezo-mobile-prefs", JSON.stringify({ onboarded: true, apiUrl: "", language: "uz" })));
  await page.goto("https://ezo-mobile.test/");
  await page.locator('nav button[data-go="chat"]').click();
  await page.locator("#mic").click();
  await expect(page.locator("#cameraToggle")).toBeEnabled({ timeout: 20_000 });
  await expect(page.locator("#clapState")).toHaveAttribute("data-microphone", "off");
  await page.locator("#cameraToggle").click();
  await expect(page.locator("#cameraState")).toHaveAttribute("data-camera", /tracking|lost/, { timeout: 60_000 });
  await expect.poll(async () => Number(await page.locator("#voiceStage").getAttribute("data-fps")), { timeout: 30_000 }).toBeGreaterThan(0);
  await shot(page, "android-stage");
  await page.locator("#stageClose").click();
  await expect(page.locator("#voiceStage")).toBeHidden();
  expect(await page.evaluate(() => (document.getElementById("perceptionVideo") as HTMLVideoElement).srcObject)).toBeNull();
  await page.locator("#mic").click();
  await expect(page.locator("#cameraState")).toHaveAttribute("data-camera", "off");
});
