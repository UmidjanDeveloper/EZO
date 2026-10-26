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
  },
  en: { idle: "EZO", idleHint: "{shortcut} — speak", thinking: "Thinking…", thinkingHint: "Request sent", offline: "EZO offline", offlineHint: "Cannot reach the server", stopped: "Stopped", you: "You", talk: "Start or stop talking", type: "Ask by typing", stop: "Stop", settings: "Settings", typePlaceholder: "For example: open the calculator", history: "Conversation history", newConversation: "New conversation", noHistory: "No messages yet.", showHideHint: "Show/hide: Ctrl+Alt+H" },
};

async function openPill(page: Page, options: { language?: "uz" | "en"; online?: boolean; ai?: boolean; replyDelayMs?: number } = {}) {
  await page.addInitScript(
    ({ strings, language, online, ai, replyDelayMs }) => {
      const listeners: Record<string, ((payload: unknown) => void)[]> = {};
      const on = (channel: string) => (callback: (payload: unknown) => void) => (listeners[channel] ??= []).push(callback);
      const w = window as unknown as Record<string, unknown>;
      w.__calls = [] as string[];
      w.__emit = (channel: string, payload: unknown) => (listeners[channel] ?? []).forEach((cb) => cb(payload));
      let cancelled = false;
      w.ezo = {
        init: async () => ({ strings, shortcut: "Ctrl+Alt+Space", language, status: { online, ai, voice: ai, text: online ? (ai ? "ready" : "no ai") : "offline" } }),
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
      };
    },
    { strings: STRINGS[options.language ?? "uz"], language: options.language ?? "uz", online: options.online ?? true, ai: options.ai ?? true, replyDelayMs: options.replyDelayMs ?? 50 },
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
  await openPill(page);
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
