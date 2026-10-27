import { expect, test, type Page } from "@playwright/test";
import { execSync } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";

// The real Electron pill renderer (apps/desktop/dist/pill.html, built by esbuild) in
// Chromium, with the main-process bridge replaced by a recording fake. Electron itself
// (windows, tray, IPC wiring) is exercised by the Windows self-test in CI; this covers what
// the owner sees: states, words in their language, server status, history, task progress
// and a stop that really cancels.

const DESKTOP = path.resolve(__dirname, "../../../apps/desktop");
const PILL = path.join(DESKTOP, "dist", "pill.html");

const STRINGS = {
  uz: {
    idle: "EZO", idleHint: "{shortcut} — gapiring", listening: "Tinglayapman…", listeningHint: "Tugatish uchun yana bosing",
    recognizing: "Taniyapman…", recognizingHint: "Eshitganimni matnga aylantiryapman", thinking: "O‘ylayapman…", thinkingHint: "EZO serveriga so‘rov yuborildi",
    working: "Bajaryapman…", workingHint: "Kompyuterda amal bajarilmoqda", speaking: "Gapiryapman…", speakingHint: "To‘xtatish uchun ■",
    success: "Bajarildi", successHint: "", error: "Xatolik", errorHint: "Batafsil pastda", offline: "EZO oflayn", offlineHint: "Serverga ulanib bo‘lmayapti",
    stopped: "To‘xtatildi", you: "Siz", history: "Suhbat tarixi", newConversation: "Yangi suhbat", noHistory: "Bu suhbatda hali xabar yo‘q.",
    taskRunning: "JARVIS vazifasi: {step}", taskWaiting: "JARVIS: sizning tasdig‘ingizni kutyapti", cancelTask: "Vazifani bekor qilish",
    talk: "Gapirishni boshlash yoki to‘xtatish", type: "Yozib so‘rash", stop: "To‘xtatish", settings: "Sozlamalar", typePlaceholder: "Masalan: Kalkulyatorni och",
    acted: "Bajarildi", showHideHint: "Ko‘rsatish/yashirish: Ctrl+Alt+H",
    expand: "Kattalashtirish", collapse: "Kichraytirish", micActive: "Mikrofon faol", micOff: "Mikrofon sozlamalarda o‘chirilgan", cameraActive: "Kamera faol",
    cameraOff: "Kamera o‘chiq", cameraOn: "Kamerani yoqish", cameraStop: "Kamerani to‘xtatish", cameraSettings: "Kamera sozlamalarda o‘chirilgan — avval u yerda yoqing.",
    cameraUnavailable: "Kamera kuzatuvi bu versiyada yo‘q: sensing dvigateli (yuz/qo‘l) hali ulanmagan.", cameraDenied: "Kameraga ruxsat berilmadi.", cameraRequesting: "Kamera so‘ralmoqda…",
    cameraTracking: "Kamera: yuz ko‘rinmoqda", cameraLost: "Kamera: yuz topilmadi", cameraPrivacy: "Tasvir kompyuteringizdan chiqmaydi, yozib olinmaydi, yuz tanilmaydi.",
    attentionPointer: "EZO sichqonchaga qaraydi (kamera emas)", attentionHand: "EZO qo‘lingizga qaraydi", attentionHead: "EZO sizga qaraydi", attentionSimulated: "SIMULYATSIYA — haqiqiy kamera emas",
    lowPower: "Tejamkor rejim: 30 kadr/s", clap: "Qarsak eshitildi",
    cameraAssetsMissing: "Kamera modeli bu buildga qo‘shilmagan (vision assets yo‘q).", cameraAssetsInvalid: "Kamera modeli tekshiruvdan o‘tmadi: {detail}",
    cameraEngine: "Yuz/qo‘l kuzatuvi: MediaPipe, shu kompyuterda; kadrlar hech qayerga yuborilmaydi.", cameraError: "Kamera xatosi: {detail}",
    clapListen: "Qarsakni tinglash", clapStop: "Tinglashni to‘xtatish", clapOff: "Qarsak mikrofoni o‘chiq", clapRequesting: "Mikrofon so‘ralmoqda…", clapActive: "Mikrofon (qarsak) faol",
    clapDenied: "Mikrofonga ruxsat berilmadi — «Qarsakni tinglash»ni qayta bosing.", clapError: "Mikrofon xatosi: {detail}", clapPrivacy: "Faqat qarsak kabi qisqa tovushlar aniqlanadi.",
    clapSettings: "Qarsakni tinglash sozlamalarda o‘chiq — avval u yerda yoqing.", clapUnavailable: "Ovoz provayderi yo‘q — javob aytilmadi.",
  },
  en: { idle: "EZO", idleHint: "{shortcut} — speak", thinking: "Thinking…", thinkingHint: "Request sent", offline: "EZO offline", offlineHint: "Cannot reach the server", stopped: "Stopped", you: "You", talk: "Start or stop talking", type: "Ask by typing", stop: "Stop", settings: "Settings", typePlaceholder: "For example: open the calculator", history: "Conversation history", newConversation: "New conversation", noHistory: "No messages yet.", showHideHint: "Show/hide: Ctrl+Alt+H" },
};

interface PillOptions {
  language?: "uz" | "en";
  online?: boolean;
  ai?: boolean;
  replyDelayMs?: number;
  media?: { microphone: boolean; camera: boolean };
}

async function openPill(page: Page, options: PillOptions = {}) {
  await page.addInitScript(
    ({ strings, language, online, ai, replyDelayMs, media }) => {
      const listeners: Record<string, ((payload: unknown) => void)[]> = {};
      const on = (channel: string) => (callback: (payload: unknown) => void) => (listeners[channel] ??= []).push(callback);
      const w = window as unknown as Record<string, unknown>;
      w.__calls = [] as string[];
      w.__emit = (channel: string, payload: unknown) => (listeners[channel] ?? []).forEach((cb) => cb(payload));
      let cancelled = false;
      w.ezo = {
        init: async () => ({ strings, shortcut: "Ctrl+Alt+Space", language, status: { online, ai, voice: ai, text: online ? (ai ? "ready" : "no ai") : "offline" }, media, lowPower: false }),
        sendText: async (text: string) => {
          (w.__calls as string[]).push(`text:${text}`);
          cancelled = false;
          await new Promise((r) => setTimeout(r, replyDelayMs));
          if (cancelled) return { cancelled: true };
          return text.includes("kalkulyator") ? { transcript: text, reply: "Kalkulyator ochildi.", acted: true } : { transcript: text, reply: `Javob: ${text}` };
        },
        sendAudio: async () => ({ error: "no audio in this test" }),
        cancelTurn: () => {
          (w.__calls as string[]).push("cancel");
          cancelled = true;
        },
        openSettings: () => (w.__calls as string[]).push("settings"),
        setFocusable: () => undefined,
        setHeight: (h: number) => (w.__calls as string[]).push(`height:${h}`),
        setExpanded: (next: boolean) => {
          (w.__calls as string[]).push(`expanded:${next}`);
          (listeners.expanded ?? []).forEach((cb) => cb(next));
        },
        refreshStatus: async () => ({ online, ai, voice: ai, text: "" }),
        recentHistory: async () => ({ ok: true, conversationId: "c1", messages: [{ role: "user", content: "Salom" }, { role: "assistant", content: "Salom! Qanday yordam beray?" }] }),
        conversations: async () => ({ ok: true, conversations: [{ id: "c1", title: "Salom" }, { id: "c2", title: "Hisobot" }] }),
        switchConversation: async (id: string | null) => {
          (w.__calls as string[]).push(`switch:${id}`);
          return id;
        },
        tasks: async () => [],
        cancelTask: async (id: string) => {
          (w.__calls as string[]).push(`cancelTask:${id}`);
          return { ok: true };
        },
        onToggle: on("shortcut:toggle"),
        onNotice: on("notice"),
        onError: on("error"),
        onStage: on("stage"),
        onStatus: on("status"),
        onTasks: on("tasks"),
        onInit: on("init"),
        onVisibility: on("visibility"),
        onExpanded: on("expanded"),
      };
    },
    {
      strings: STRINGS[options.language ?? "uz"],
      language: options.language ?? "uz",
      online: options.online ?? true,
      ai: options.ai ?? true,
      replyDelayMs: options.replyDelayMs ?? 50,
      media: options.media ?? { microphone: true, camera: false },
    },
  );
  await page.goto(`file://${PILL}`);
  await expect(page.locator("#pill")).toHaveClass(/idle|offline/);
}

const calls = (page: Page) => page.evaluate(() => (window as unknown as { __calls: string[] }).__calls);
const emit = (page: Page, channel: string, payload: unknown) =>
  page.evaluate(([c, p]) => (window as unknown as { __emit: (c: string, p: unknown) => void }).__emit(c, p), [channel, payload] as const);

test.beforeAll(() => {
  if (!existsSync(PILL)) execSync("pnpm --filter @ezo/desktop build", { cwd: path.resolve(DESKTOP, "../.."), stdio: "inherit" });
});

test("desktop pill: words, shortcut and server status come from the main process", async ({ page }) => {
  await openPill(page, { language: "en" });
  await expect(page.locator("#hint")).toHaveText("Ctrl+Alt+Space — speak");
  await expect(page.locator("#orb")).toHaveAttribute("aria-label", "Start or stop talking");
  await expect(page.locator("#question")).toHaveAttribute("placeholder", "For example: open the calculator");
  await expect(page.locator("#dot")).toHaveClass(/online/);
  expect(await page.evaluate(() => document.documentElement.lang)).toBe("en");
  // The server goes away: the figure and the words say so, nothing pretends to be connected.
  await emit(page, "status", { online: false, ai: false, voice: false, text: "Cannot reach the EZO server" });
  await expect(page.locator("#pill")).toHaveClass(/offline/);
  await expect(page.locator("#label")).toHaveText("EZO offline");
  await expect(page.locator("#dot")).toHaveClass(/offline/);
  await expect(page.locator("#dot")).toHaveAttribute("aria-label", "Cannot reach the EZO server");
  await expect(page.locator("#face")).toHaveAttribute("data-state", "offline");
  // A server without an AI provider is amber, not green.
  await emit(page, "status", { online: true, ai: false, voice: false, text: "no ai" });
  await expect(page.locator("#dot")).toHaveClass(/noai/);
  await expect(page.locator("#pill")).toHaveClass(/idle/);
});

test("desktop pill: a typed turn goes thinking → working → success and shows the reply", async ({ page }) => {
  await openPill(page, { replyDelayMs: 1200 }); // a server answer takes a moment; the stage arrives meanwhile
  await page.locator("#keyboard").click();
  await page.locator("#question").fill("kalkulyatorni och");
  await page.locator("#question").press("Enter");
  await expect(page.locator("#pill")).toHaveClass(/thinking/);
  await emit(page, "stage", "working");
  await expect(page.locator("#label")).toHaveText("Bajaryapman…");
  await expect(page.locator("#face")).toHaveAttribute("data-state", "working");
  await expect(page.locator("#reply")).toHaveText("Kalkulyator ochildi.");
  await expect(page.locator("#transcript")).toHaveText("Siz: kalkulyatorni och");
  await expect(page.locator("#pill")).toHaveClass(/success/);
  await expect(page.locator("#face")).toHaveAttribute("aria-label", "Bajarildi");
  await expect(page.locator("#pill")).toHaveClass(/idle/, { timeout: 5000 }); // success is a moment
  // A stage that arrives after the turn ended must not wake the pill up again.
  await emit(page, "stage", "working");
  await page.waitForTimeout(200);
  await expect(page.locator("#pill")).toHaveClass(/idle/);
});

test("desktop pill: stop during thinking really cancels the request and ignores a late reply", async ({ page }) => {
  await openPill(page, { replyDelayMs: 1500 });
  await page.locator("#keyboard").click();
  await page.locator("#question").fill("uzoq savol");
  await page.locator("#question").press("Enter");
  await expect(page.locator("#pill")).toHaveClass(/thinking/);
  await page.locator("#stop").click();
  await expect(page.locator("#pill")).toHaveClass(/idle/);
  await expect(page.locator("#hint")).toHaveText("To‘xtatildi");
  await page.waitForTimeout(1800);
  await expect(page.locator("#reply")).toHaveText(""); // the late reply was not shown
  expect(await calls(page)).toContain("cancel");
});

test("desktop pill: the conversation history comes from the server and can be switched", async ({ page }) => {
  await openPill(page);
  await page.locator("#history").click();
  const items = page.locator("#messages li");
  await expect(items).toHaveCount(2);
  await expect(items.nth(0)).toHaveClass(/me/);
  await expect(items.nth(1)).toHaveText("Salom! Qanday yordam beray?");
  await expect(page.locator("#conversations")).toHaveValue("c1");
  await page.locator("#conversations").selectOption("c2");
  expect(await calls(page)).toContain("switch:c2");
  await page.locator("#newConversation").click();
  expect(await calls(page)).toContain("switch:null");
});

test("desktop pill: JARVIS progress is shown honestly and can be cancelled; notices are not errors", async ({ page }) => {
  await openPill(page);
  await emit(page, "tasks", [{ id: "t1", state: "running", step: "document.convert_pdf", waiting: false, report: "" }]);
  await expect(page.locator("#task")).toBeVisible();
  await expect(page.locator("#taskText")).toHaveText("JARVIS vazifasi: document.convert_pdf");
  await expect(page.locator("#face")).toHaveAttribute("data-state", "working");
  await emit(page, "tasks", [{ id: "t1", state: "running", step: "telegram.send", waiting: true, report: "" }]);
  await expect(page.locator("#taskText")).toHaveText("JARVIS: sizning tasdig‘ingizni kutyapti");
  await page.locator("#cancelTask").click();
  expect(await calls(page)).toContain("cancelTask:t1");
  await emit(page, "tasks", []);
  await expect(page.locator("#task")).toBeHidden();
  await emit(page, "notice", "Hisobot Telegram’ga yuborildi.");
  await expect(page.locator("#reply")).toHaveText("Hisobot Telegram’ga yuborildi.");
  await expect(page.locator("#pill")).not.toHaveClass(/error/);
  await emit(page, "error", "Telegram javob bermadi.");
  await expect(page.locator("#pill")).toHaveClass(/error/);
});

test("desktop stage: expands to the full humanoid and collapses back, ten times, without leaking", async ({ page }) => {
  await openPill(page);
  await expect(page.locator("#face")).toHaveAttribute("data-ezo-avatar", "webgl");
  const heap = () => page.evaluate(() => (performance as unknown as { memory?: { usedJSHeapSize: number } }).memory?.usedJSHeapSize ?? 0);
  const before = await heap();
  for (let i = 0; i < 10; i++) {
    await page.locator("#expand").click();
    await expect(page.locator("#stage")).toBeVisible();
    await expect(page.locator("#stageFace")).toHaveAttribute("data-ezo-avatar", "webgl");
    await expect(page.locator("#stageFace")).toHaveAttribute("data-state", "idle");
    await expect(page.locator("#stageFrame svg")).toHaveCount(1);
    await page.locator("#expand").click();
    await expect(page.locator("#stage")).toBeHidden();
  }
  expect((await calls(page)).filter((c) => c === "expanded:true")).toHaveLength(10);
  // One voice frame at most, never ten stacked, and no runaway heap.
  await page.locator("#expand").click();
  await expect(page.locator("#stageFrame svg")).toHaveCount(1);
  const after = await heap();
  expect(after - before).toBeLessThan(40 * 1024 * 1024);
  // The pointer is a labelled fallback for the camera.
  await page.locator("#stageFace").hover({ position: { x: 20, y: 20 } });
  await expect(page.locator("#attention")).toHaveText("EZO sichqonchaga qaraydi (kamera emas)");
});

test("desktop stage: served from file:// (no app origin) the camera and clap controls stay disabled and say why", async ({ page }) => {
  // The real app serves itself from https://ezo.desktop; here vision-assets.json cannot be
  // fetched, so the honest state is "disabled with a reason", never a pretended camera.
  await openPill(page, { media: { microphone: true, camera: true } });
  await page.locator("#expand").click();
  await expect(page.locator("#cameraToggle")).toBeDisabled();
  await expect(page.locator("#cameraPrivacy")).toContainText("Kamera xatosi");
  await expect(page.locator("#cameraState")).toHaveAttribute("data-camera", "off");
  await expect(page.locator("#clapToggle")).toBeDisabled();
  await expect(page.locator("#media")).toBeEmpty(); // no camera, no microphone: no indicator
});

test("desktop pill: with the microphone switched off in settings, talking is refused honestly", async ({ page }) => {
  await openPill(page, { media: { microphone: false, camera: false } });
  await page.locator("#orb").click();
  await expect(page.locator("#pill")).toHaveClass(/error/);
  await expect(page.locator("#hint")).toHaveText("Mikrofon sozlamalarda o‘chirilgan");
  await expect(page.locator("#media")).toBeEmpty();
});
