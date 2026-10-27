/**
 * EZO desktop: a small always-on-top pill. Ctrl+Alt+Space (by default) starts and stops
 * listening; the recording goes to the EZO API for speech-to-text, the words are either
 * a registered local action (only if the owner allowed it) or a normal conversation,
 * and the reply is spoken back. The renderer never sees the API token.
 */
import { execFile, spawn } from "node:child_process";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import {
  app,
  BrowserWindow,
  clipboard,
  desktopCapturer,
  dialog,
  globalShortcut,
  ipcMain,
  Menu,
  nativeImage,
  net,
  protocol,
  safeStorage,
  screen,
  session,
  shell,
  Tray,
} from "electron";
import { createActions } from "./actions";
import { createEzoClient, EzoApiError, type JarvisTaskView, type ServerStatus } from "./api";
import { createAssistant } from "./assistant";
import { findFiles, isInsideAllowed } from "./files";
import { buildResult, generateDeviceKey, latestDocuments, pairingRequest, validWork, type DeviceKey } from "./jarvis";
import type { Lang } from "./replies";
import { runSelfTest } from "./selftest";
import { ALLOWED_SHORTCUTS, sanitizeSettings, type DesktopSettings } from "./settings";
import { format, strings, UI_LANGUAGES } from "./strings";

const SETTINGS_FILE = () => path.join(app.getPath("userData"), "settings.json");
const TOKEN_FILE = () => path.join(app.getPath("userData"), "token.bin");
const JARVIS_KEY_FILE = () => path.join(app.getPath("userData"), "jarvis-key.bin");
const JARVIS_POLL_MS = 5_000;
const STATUS_POLL_MS = 30_000;
const SHOW_HIDE_SHORTCUT = "Control+Alt+H";
const MAX_AUDIO_BYTES = 10 * 1024 * 1024;

/**
 * The renderers load from https://ezo.desktop/, served from dist/ by a protocol handler.
 * A real https origin (not file://) is what the perception worker needs to fetch the
 * bundled, SHA256-pinned vision assets from "the same origin" with a strict CSP; nothing
 * ever goes to the network for that host, and every other https request from a renderer
 * is passed through untouched (renderers have connect-src 'self' anyway).
 */
const APP_ORIGIN = "https://ezo.desktop";
const CONTENT_TYPES: Record<string, string> = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript",
  ".css": "text/css",
  ".json": "application/json",
  ".wasm": "application/wasm",
  ".task": "application/octet-stream",
  ".txt": "text/plain; charset=utf-8",
  ".png": "image/png",
};

function serveAppOrigin(): void {
  protocol.handle("https", (request) => {
    const url = new URL(request.url);
    if (url.origin !== APP_ORIGIN) return net.fetch(request, { bypassCustomProtocolHandlers: true });
    const relative = path.normalize(decodeURIComponent(url.pathname)).replace(/^([/\\])+/, "");
    const file = path.join(__dirname, relative);
    if (!file.startsWith(__dirname + path.sep) || !existsSync(file)) return new Response("not found", { status: 404 });
    const extension = path.extname(file).toLowerCase();
    const headers: Record<string, string> = { "Content-Type": CONTENT_TYPES[extension] ?? "application/octet-stream", "Cache-Control": "no-store" };
    // The perception worker may compile the bundled WASM and importScripts its verified loader (a blob it made itself); nothing remote.
    if (relative.endsWith("vision.worker.js")) headers["Content-Security-Policy"] = "default-src 'none'; script-src 'self' blob: 'wasm-unsafe-eval'; connect-src 'self' blob:";
    return new Response(readFileSync(file), { headers });
  });
}

let pill: BrowserWindow | null = null;
/** Small pill (one row) or the expanded stage with the full humanoid. */
let expanded = false;
const PILL_SIZE = { width: 360, height: 72 } as const;
const STAGE_SIZE = { width: 420, height: 640 } as const;
let settingsWindow: BrowserWindow | null = null;
let tray: Tray | null = null;
let settings: DesktopSettings = sanitizeSettings({});
const t = () => strings(settings.language);

function loadSettings(): boolean {
  try {
    settings = sanitizeSettings(JSON.parse(readFileSync(SETTINGS_FILE(), "utf8")));
    return true;
  } catch {
    settings = sanitizeSettings({});
    return false;
  }
}

function saveSettings(next: DesktopSettings): void {
  settings = sanitizeSettings(next);
  writeFileSync(SETTINGS_FILE(), JSON.stringify(settings, null, 2), { mode: 0o600 });
}

/** The token is stored only encrypted by the OS (DPAPI on Windows); never in plain text. */
function readToken(): string | null {
  if (!existsSync(TOKEN_FILE()) || !safeStorage.isEncryptionAvailable()) return null;
  try {
    return safeStorage.decryptString(readFileSync(TOKEN_FILE()));
  } catch {
    return null;
  }
}

function writeToken(token: string | null): boolean {
  if (!token) {
    if (existsSync(TOKEN_FILE())) writeFileSync(TOKEN_FILE(), Buffer.alloc(0));
    return true;
  }
  if (!safeStorage.isEncryptionAvailable()) return false;
  writeFileSync(TOKEN_FILE(), safeStorage.encryptString(token), { mode: 0o600 });
  return true;
}

/** The JARVIS device key, encrypted by the OS like the token; never sent anywhere. */
function readDeviceKey(): DeviceKey | null {
  if (!existsSync(JARVIS_KEY_FILE()) || !safeStorage.isEncryptionAvailable()) return null;
  try {
    return JSON.parse(safeStorage.decryptString(readFileSync(JARVIS_KEY_FILE()))) as DeviceKey;
  } catch {
    return null;
  }
}

function writeDeviceKey(key: DeviceKey | null): void {
  if (!key) {
    if (existsSync(JARVIS_KEY_FILE())) writeFileSync(JARVIS_KEY_FILE(), Buffer.alloc(0));
    return;
  }
  writeFileSync(JARVIS_KEY_FILE(), safeStorage.encryptString(JSON.stringify(key)), { mode: 0o600 });
}

const client = (signal?: AbortSignal) => createEzoClient(settings.apiUrl, readToken(), fetch, { lang: settings.language, signal });

// --- what the pill is told ---------------------------------------------------------------

type PillStage = "recognizing" | "thinking" | "working";
interface PillStatus {
  online: boolean;
  ai: boolean;
  voice: boolean;
  text: string;
}
let lastStatus: PillStatus = { online: false, ai: false, voice: false, text: "" };

function tell(channel: "notice" | "error" | "stage" | "status" | "tasks" | "init" | "visibility", payload: unknown): void {
  pill?.webContents.send(channel, payload);
}

/** Checks the server, then tells the pill and the tray. Called on a timer and after each turn. */
async function refreshStatus(): Promise<PillStatus> {
  let next: PillStatus;
  try {
    const status: ServerStatus = await client().status();
    next = { online: true, ai: status.ai, voice: status.voice, text: status.ai ? t().pill.statusOnline : t().pill.statusNoAi };
  } catch (error) {
    // /api/status needs a valid token; a reachable server with a bad token is still "online".
    const reachable = error instanceof EzoApiError && error.status > 0;
    next = reachable ? { online: true, ai: false, voice: false, text: error instanceof EzoApiError ? error.message : t().pill.statusOffline } : { online: false, ai: false, voice: false, text: t().pill.statusOffline };
  }
  lastStatus = next;
  tell("status", next);
  tray?.setToolTip(format(t().tray.tooltip, { status: next.text }));
  return next;
}

interface PillInit {
  strings: ReturnType<typeof strings>["pill"];
  shortcut: string;
  language: Lang;
  status: PillStatus;
  /** What the owner allowed in settings; the renderer never asks the OS for more. */
  media: { microphone: boolean; camera: boolean };
  lowPower: boolean;
  voiceVolume: number;
  clap: { listening: boolean; startsListening: boolean };
  build: { version: string; sha: string };
}
const BUILD_SHA = process.env.EZO_BUILD_SHA ?? "dev";

function pillInit(): PillInit {
  return {
    strings: t().pill,
    shortcut: settings.shortcut.replace("Control", "Ctrl"),
    language: settings.language,
    status: lastStatus,
    media: { microphone: settings.allowMicrophone, camera: settings.allowCamera },
    lowPower: settings.lowPower,
    voiceVolume: settings.voiceVolume,
    clap: { listening: settings.clapListening, startsListening: settings.clapStartsListening },
    build: { version: app.getVersion(), sha: BUILD_SHA },
  };
}

/** The pill's latest Diagnostics numbers (no images, audio or landmarks), shown in the settings window. */
let diagnostics: Record<string, unknown> = {};

// --- JARVIS companion ----------------------------------------------------------------------

let jarvisBusy = false;
const trackedTasks = new Map<string, JarvisTaskView>();
const askedSteps = new Set<string>();

function taskSummaries(): { id: string; state: string; step: string | null; waiting: boolean; report: string }[] {
  return [...trackedTasks.values()].map((task) => {
    const current = task.steps.find((s) => !["completed", "skipped", "cancelled"].includes(s.state));
    return {
      id: task.id,
      state: task.state,
      step: current?.action ?? null,
      waiting: current?.state === "awaiting_authorization",
      report: task.report,
    };
  });
}

/** Native approval for the exact external action the server computed (recipient + file
 * hashes); the decision echoes the server's scope hash so nothing else can be approved. */
async function followTasks(): Promise<void> {
  const api = client();
  for (const taskId of [...trackedTasks.keys()]) {
    let task: JarvisTaskView;
    try {
      task = await api.jarvisTask(taskId);
    } catch (error) {
      if (error instanceof EzoApiError && error.status === 404) trackedTasks.delete(taskId);
      continue; // one unreachable task must not stop the others
    }
    trackedTasks.set(taskId, task);
    const step = task.steps.find((s) => s.state === "awaiting_authorization" && s.scope_sha256);
    if (step && !askedSteps.has(step.id)) {
      askedSteps.add(step.id);
      tell("tasks", taskSummaries());
      const files = (step.output.documents ?? []).map((d) => `• ${d.filename} (${d.sha256.slice(0, 12)}…)`).join("\n");
      const recipient = `${step.output.recipient ?? "?"}${step.output.telegram_name ? ` (${step.output.telegram_name})` : ""}`;
      const { response } = await dialog.showMessageBox({
        type: "warning",
        buttons: [t().dialogs.allowSend, t().dialogs.deny],
        defaultId: 1,
        cancelId: 1,
        title: t().dialogs.jarvisApproveTitle,
        message: format(t().dialogs.sendTo, { recipient }),
        detail: files,
      });
      await api.decideJarvisStep(task.id, step.id, step.scope_sha256!, response === 0);
      continue;
    }
    if (["completed", "failed", "cancelled"].includes(task.state)) {
      trackedTasks.delete(taskId);
      tell(task.state === "completed" ? "notice" : "error", task.report || format(t().dialogs.taskReport, { state: task.state }));
    }
  }
  tell("tasks", taskSummaries());
}

/** Poll the owner's EZO server for this device's JARVIS work; ask the owner before
 * any file leaves the computer; sign and return the result. */
async function pollJarvis(): Promise<void> {
  const deviceId = settings.jarvisDeviceId;
  const key = readDeviceKey();
  if (jarvisBusy || !deviceId || !key) {
    if (!jarvisBusy && trackedTasks.size > 0) await followTasks().catch(() => undefined);
    return;
  }
  jarvisBusy = true;
  try {
    const api = client();
    for (const item of await api.deviceWork(deviceId)) {
      if (!validWork(item, deviceId, Math.floor(Date.now() / 1000))) continue;
      let outcome: Parameters<typeof buildResult>[2];
      if (!settings.jarvisFolder) {
        outcome = { refused: "No folder is allowed for JARVIS on this computer." };
      } else {
        const latest = await latestDocuments(settings.jarvisFolder, item.count, item.extensions);
        const names = latest.files.map((f) => `• ${f.name}`).join("\n") || t().dialogs.noFiles;
        const { response } = await dialog.showMessageBox({
          type: "question",
          buttons: [t().dialogs.send, t().dialogs.deny],
          defaultId: 1,
          cancelId: 1,
          title: t().dialogs.jarvisTitle,
          message: t().dialogs.filesRequest,
          detail: `${names}\n\n${format(t().dialogs.filesDetail, { folder: settings.jarvisFolder })}`,
        });
        outcome = response === 0 ? latest : { refused: "The owner declined on the device." };
      }
      const result = await buildResult(item, key, outcome);
      const task = await api.submitDeviceResult(deviceId, result);
      tell("notice", task.report || format(t().dialogs.taskReport, { state: task.state }));
    }
    await followTasks();
  } catch (error) {
    if (error instanceof EzoApiError && (error.code === "not_paired" || error.status === 404)) {
      saveSettings({ ...settings, jarvisDeviceId: null });
    }
  } finally {
    jarvisBusy = false;
  }
}

// --- local actions -------------------------------------------------------------------------

const GUI_APPS = new Set(["calc.exe", "notepad.exe", "mspaint.exe", "explorer.exe"]);

/** No shell: fixed executable + argument array. GUI apps resolve once started. */
function run(file: string, args: readonly string[]): Promise<void> {
  if (GUI_APPS.has(file)) {
    return new Promise((resolve, reject) => {
      const child = spawn(file, [...args], { detached: true, stdio: "ignore" });
      child.once("spawn", () => {
        child.unref();
        resolve();
      });
      child.once("error", reject);
    });
  }
  return new Promise((resolve, reject) => {
    execFile(file, [...args], { windowsHide: true, timeout: 15_000 }, (error) => (error ? reject(error) : resolve()));
  });
}

const actions = createActions({
  platform: process.platform,
  run,
  clipboard,
  openPath: (target) => shell.openPath(target),
  sleep: (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
});

async function captureScreen(): Promise<Uint8Array> {
  const display = screen.getPrimaryDisplay();
  const scale = Math.min(1, 1600 / display.size.width);
  const sources = await desktopCapturer.getSources({
    types: ["screen"],
    thumbnailSize: {
      width: Math.round(display.size.width * scale),
      height: Math.round(display.size.height * scale),
    },
  });
  const source = sources.find((s) => s.display_id === String(display.id)) ?? sources[0];
  if (!source || source.thumbnail.isEmpty()) throw new Error(t().dialogs.screenshotFailed);
  // Hide nothing, keep nothing: the PNG lives only in memory for this one request.
  return new Uint8Array(source.thumbnail.toPNG());
}

// --- one turn ------------------------------------------------------------------------------

let currentTurn: AbortController | null = null;

const assistant = createAssistant({
  settings: () => settings,
  client: () => client(currentTurn?.signal),
  actions,
  findFiles,
  isInsideAllowed,
  confirm: async (message) => {
    const { response } = await dialog.showMessageBox({
      type: "question",
      buttons: [t().dialogs.allow, t().dialogs.cancel],
      defaultId: 1,
      cancelId: 1,
      title: "EZO",
      message,
    });
    return response === 0;
  },
  captureScreen,
  saveConversation: (id) => saveSettings({ ...settings, conversationId: id }),
  trackTask: (id) => {
    trackedTasks.set(id, { id, state: "queued", report: "", steps: [] });
    void pollJarvis();
  },
  onStage: (stage) => tell("stage", stage),
});

interface TurnResponse {
  transcript?: string;
  reply?: string;
  acted?: boolean;
  audio?: { mimeType: string; data: Uint8Array };
  error?: string;
  notice?: string;
  cancelled?: boolean;
}

async function respond(text: string, heard: Lang | null = null): Promise<TurnResponse> {
  const result = await assistant.handle(text, heard);
  const out: TurnResponse = { transcript: text, reply: result.reply, acted: result.acted };
  if (settings.speakReplies && !currentTurn?.signal.aborted) {
    try {
      out.audio = await client(currentTurn?.signal).speak(result.reply, result.language);
    } catch (error) {
      if (error instanceof EzoApiError && error.code === "cancelled") return { cancelled: true };
      out.notice = error instanceof EzoApiError ? error.message : t().pill.readAloudFailed;
    }
  }
  return out;
}

function failure(error: unknown): TurnResponse {
  if (error instanceof EzoApiError && error.code === "cancelled") return { cancelled: true };
  if (error instanceof EzoApiError && error.code === "network") void refreshStatus();
  return { error: error instanceof EzoApiError ? error.message : `${t().pill.error}: ${(error as Error).message}` };
}

/** Runs one turn with its own abort controller; a stop from the pill cancels the requests. */
async function turn(body: () => Promise<TurnResponse>): Promise<TurnResponse> {
  currentTurn?.abort();
  const controller = new AbortController();
  currentTurn = controller;
  try {
    const result = await body();
    return controller.signal.aborted ? { cancelled: true } : result;
  } catch (error) {
    return failure(error);
  } finally {
    if (currentTurn === controller) currentTurn = null;
    if (!controller.signal.aborted && !lastStatus.online) void refreshStatus();
  }
}

// --- windows -------------------------------------------------------------------------------

function secureWindow(win: BrowserWindow): void {
  win.webContents.on("will-navigate", (event) => event.preventDefault());
  win.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
}

function createPill(): void {
  const { workArea } = screen.getPrimaryDisplay();
  pill = new BrowserWindow({
    width: 360,
    height: 72,
    x: Math.round(workArea.x + workArea.width / 2 - 180),
    y: workArea.y + 12,
    frame: false,
    transparent: true,
    resizable: false,
    alwaysOnTop: true,
    skipTaskbar: true,
    focusable: false, // the app you are working in keeps focus (needed for dictation)
    show: false,
    webPreferences: {
      preload: path.join(__dirname, "preload-pill.js"),
      contextIsolation: true,
      sandbox: true,
      nodeIntegration: false,
    },
  });
  pill.setAlwaysOnTop(true, "screen-saver");
  secureWindow(pill);
  void pill.loadURL(`${APP_ORIGIN}/pill.html`);
  pill.once("ready-to-show", () => pill?.showInactive());
  // Hidden means hidden: the renderer stops the microphone, the camera and the drawing loop.
  pill.on("hide", () => tell("visibility", false));
  pill.on("show", () => tell("visibility", true));
}

function togglePill(): void {
  if (!pill) return;
  if (pill.isVisible()) pill.hide();
  else pill.showInactive();
}

/** Grows the window into the stage (the full humanoid) or back to the one-row pill. */
function setExpanded(next: boolean): void {
  if (!pill) return;
  expanded = next;
  const size = next ? STAGE_SIZE : PILL_SIZE;
  pill.setSize(size.width, size.height);
  pill.webContents.send("expanded", next);
  createTrayMenu();
}

function openSettings(): void {
  if (settingsWindow) return settingsWindow.focus();
  settingsWindow = new BrowserWindow({
    width: 560,
    height: 760,
    title: t().settings.title,
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, "preload-settings.js"),
      contextIsolation: true,
      sandbox: true,
      nodeIntegration: false,
    },
  });
  secureWindow(settingsWindow);
  void settingsWindow.loadURL(`${APP_ORIGIN}/settings.html`);
  settingsWindow.on("closed", () => {
    settingsWindow = null;
  });
}

function registerShortcut(): void {
  globalShortcut.unregisterAll();
  const ok = globalShortcut.register(settings.shortcut, () => pill?.webContents.send("shortcut:toggle"));
  if (!ok) tell("error", format(t().pill.shortcutBusy, { shortcut: settings.shortcut.replace("Control", "Ctrl") }));
  globalShortcut.register(SHOW_HIDE_SHORTCUT, togglePill);
}

function applyLanguage(): void {
  tell("init", pillInit());
  createTrayMenu();
  settingsWindow?.setTitle(t().settings.title);
  void refreshStatus();
}

function registerIpc(): void {
  ipcMain.handle("pill:init", () => pillInit());
  ipcMain.handle("turn:audio", (_event, audio: unknown, mimeType: unknown) =>
    turn(async () => {
      if (!(audio instanceof ArrayBuffer) || audio.byteLength === 0 || audio.byteLength > MAX_AUDIO_BYTES) {
        return { error: t().pill.emptyOrLarge };
      }
      const type = typeof mimeType === "string" && /^audio\/[a-z0-9.+-]+(;.*)?$/i.test(mimeType) ? mimeType : "audio/webm";
      tell("stage", "recognizing");
      const heard = await client(currentTurn?.signal).transcribe(new Uint8Array(audio), type.split(";")[0]!);
      if (!heard.text) return { error: t().pill.nothingHeard };
      return respond(heard.text, heard.language);
    }),
  );
  ipcMain.handle("turn:text", (_event, text: unknown) =>
    turn(async () => {
      if (typeof text !== "string" || !text.trim() || text.length > 4000) return { error: t().pill.badText };
      return respond(text.trim());
    }),
  );
  ipcMain.on("turn:cancel", () => currentTurn?.abort());
  // The clap acknowledgement: a short phrase through the real server voice (token stays here).
  ipcMain.handle("voice:speak", async (_event, text: unknown, language: unknown) => {
    if (typeof text !== "string" || !text.trim() || text.length > 200) return { error: t().pill.badText };
    const lang: Lang = language === "en" || language === "ru" ? language : "uz";
    try {
      const audio = await client().speak(text.trim(), lang);
      return { mimeType: audio.mimeType, data: audio.data, provider: audio.provider ?? null };
    } catch (error) {
      return { error: error instanceof EzoApiError ? error.message : String(error) };
    }
  });
  ipcMain.on("diag:update", (_event, next: unknown) => {
    if (next && typeof next === "object") diagnostics = { ...(next as Record<string, unknown>), at: new Date().toISOString() };
  });
  ipcMain.handle("diag:get", () => ({
    ...diagnostics,
    version: app.getVersion(),
    sha: BUILD_SHA,
    electron: process.versions.electron,
    platform: `${process.platform} ${process.arch}`,
    server: lastStatus,
    language: settings.language,
    media: { microphone: settings.allowMicrophone, camera: settings.allowCamera, clap: settings.clapListening },
  }));
  ipcMain.on("pill:focusable", (_event, focusable: unknown) => {
    if (!pill || typeof focusable !== "boolean") return;
    pill.setFocusable(focusable);
    if (focusable) pill.focus();
    else pill.blur();
  });
  ipcMain.on("pill:height", (_event, height: unknown) => {
    if (!pill || typeof height !== "number") return;
    const [width] = pill.getSize();
    const min = expanded ? STAGE_SIZE.height : PILL_SIZE.height;
    pill.setSize(width ?? PILL_SIZE.width, Math.max(min, Math.min(expanded ? 900 : 520, Math.round(height))));
  });
  ipcMain.on("pill:expand", (_event, next: unknown) => {
    if (typeof next === "boolean") setExpanded(next);
  });
  ipcMain.on("settings:open", openSettings);
  ipcMain.handle("status:refresh", () => refreshStatus());

  // The conversation lives on the server, shared with the phone and the web app.
  ipcMain.handle("history:recent", async () => {
    try {
      if (!settings.conversationId) return { ok: true, conversationId: null, messages: [] };
      const messages = await client().messages(settings.conversationId);
      return { ok: true, conversationId: settings.conversationId, messages: messages.map((m) => ({ role: m.role, content: m.content })) };
    } catch (error) {
      if (error instanceof EzoApiError && error.status === 404) {
        saveSettings({ ...settings, conversationId: null }); // the conversation is gone (deleted elsewhere)
        return { ok: true, conversationId: null, messages: [] };
      }
      return { ok: false, message: error instanceof EzoApiError ? error.message : t().pill.historyUnavailable };
    }
  });
  ipcMain.handle("history:conversations", async () => {
    try {
      return { ok: true, conversations: await client().conversations(10) };
    } catch (error) {
      return { ok: false, message: error instanceof EzoApiError ? error.message : t().pill.historyUnavailable };
    }
  });
  ipcMain.handle("history:switch", (_event, id: unknown) => {
    saveSettings({ ...settings, conversationId: typeof id === "string" ? id : null });
    return settings.conversationId;
  });

  ipcMain.handle("jarvis:tasks", () => taskSummaries());
  ipcMain.handle("jarvis:cancel-task", async (_event, id: unknown) => {
    if (typeof id !== "string" || !trackedTasks.has(id)) return { ok: false };
    try {
      const task = await client().cancelJarvisTask(id);
      trackedTasks.delete(id);
      tell("tasks", taskSummaries());
      tell("notice", t().pill.taskCancelled);
      return { ok: true, state: task.state };
    } catch (error) {
      return { ok: false, message: error instanceof EzoApiError ? error.message : String(error) };
    }
  });

  ipcMain.handle("settings:get", () => ({
    settings,
    hasToken: Boolean(readToken()),
    secureStorage: safeStorage.isEncryptionAvailable(),
    shortcuts: ALLOWED_SHORTCUTS,
    platform: process.platform,
    strings: t().settings,
    languages: UI_LANGUAGES,
  }));
  ipcMain.handle("settings:save", (_event, next: unknown) => {
    const before = settings.language;
    const merged = sanitizeSettings({
      ...settings,
      ...(next as object),
      // Folder grants and pairing change only through their own explicit flows.
      allowedFolders: settings.allowedFolders,
      jarvisFolder: settings.jarvisFolder,
      jarvisDeviceId: settings.jarvisDeviceId,
    });
    saveSettings(merged);
    registerShortcut();
    if (settings.language !== before) applyLanguage();
    else tell("init", pillInit());
    return settings;
  });
  ipcMain.handle("settings:token", (_event, token: unknown) => {
    const ok = writeToken(typeof token === "string" && token.trim() ? token.trim() : null);
    void refreshStatus();
    return ok;
  });
  ipcMain.handle("settings:add-folder", async () => {
    const result = await dialog.showOpenDialog({ properties: ["openDirectory"], title: t().dialogs.chooseFolder });
    const folder = result.filePaths[0];
    if (!result.canceled && folder) saveSettings({ ...settings, allowedFolders: [...settings.allowedFolders, folder] });
    return settings;
  });
  ipcMain.handle("settings:remove-folder", (_event, folder: unknown) => {
    saveSettings({ ...settings, allowedFolders: settings.allowedFolders.filter((f) => f !== folder) });
    return settings;
  });
  ipcMain.handle("settings:forget-conversation", () => {
    saveSettings({ ...settings, conversationId: null });
    return settings;
  });
  ipcMain.handle("jarvis:choose-folder", async () => {
    const result = await dialog.showOpenDialog({
      properties: ["openDirectory"],
      title: t().dialogs.chooseJarvisFolder,
      defaultPath: app.getPath("downloads"),
    });
    const folder = result.filePaths[0];
    if (!result.canceled && folder) saveSettings({ ...settings, jarvisFolder: folder });
    return settings;
  });
  ipcMain.handle("jarvis:clear-folder", () => {
    saveSettings({ ...settings, jarvisFolder: null });
    return settings;
  });
  ipcMain.handle("jarvis:pair", async () => {
    if (!safeStorage.isEncryptionAvailable()) return { ok: false, message: t().dialogs.noSecureStorage };
    const api = client();
    // Pairing again replaces the old device: revoke it first so one computer is one device.
    if (settings.jarvisDeviceId) await api.revokeDevice(settings.jarvisDeviceId).catch(() => undefined);
    const key = generateDeviceKey();
    try {
      const body = pairingRequest(key, `EZO — ${process.env.COMPUTERNAME ?? "PC"}`.slice(0, 80), process.platform === "win32" ? "windows" : "linux");
      const paired = await api.requestPairing(body);
      writeDeviceKey(key);
      saveSettings({ ...settings, jarvisDeviceId: paired.device.id });
      return { ok: true, code: paired.code, message: t().dialogs.pairCode };
    } catch (error) {
      return { ok: false, message: error instanceof EzoApiError ? error.message : String(error) };
    }
  });
  ipcMain.handle("jarvis:unpair", async () => {
    if (settings.jarvisDeviceId) {
      try {
        await client().revokeDevice(settings.jarvisDeviceId);
      } catch {
        // offline: the local key is still destroyed, so this PC can no longer sign results
      }
    }
    writeDeviceKey(null);
    saveSettings({ ...settings, jarvisDeviceId: null });
    return settings;
  });
  ipcMain.handle("jarvis:status", async () => {
    if (!settings.jarvisDeviceId) return { paired: false, status: "none" };
    try {
      const devices = await client().devices();
      const me = devices.find((d) => d.id === settings.jarvisDeviceId);
      return { paired: me?.status === "paired", status: me?.status ?? "unknown" };
    } catch (error) {
      return { paired: false, status: "error", message: error instanceof EzoApiError ? error.message : String(error) };
    }
  });
  ipcMain.handle("settings:test", async () => {
    const api = client();
    try {
      await api.health();
      const me = await api.me();
      const status = await refreshStatus();
      return { ok: true, message: `${format(t().dialogs.connected, { name: me.display_name ?? me.email ?? "EZO" })} — ${status.text}` };
    } catch (error) {
      void refreshStatus();
      return { ok: false, message: error instanceof EzoApiError ? error.message : String(error) };
    }
  });
}

/** Only the pill may use media, and only what the owner allowed in settings: the microphone
 * (on by default, can be switched off) and the camera (off until switched on). */
function allowOnlyAllowedMedia(): void {
  const allowedType = (type: string) => (type === "audio" ? settings.allowMicrophone : type === "video" ? settings.allowCamera : false);
  session.defaultSession.setPermissionRequestHandler((contents, permission, callback, details) => {
    const fromPill = pill !== null && contents.id === pill.webContents.id;
    const types = (details as { mediaTypes?: string[] }).mediaTypes ?? [];
    callback(Boolean(fromPill && permission === "media" && types.length > 0 && types.every(allowedType)));
  });
  session.defaultSession.setPermissionCheckHandler((contents, permission) =>
    Boolean(pill && contents?.id === pill.webContents.id && permission === "media" && (settings.allowMicrophone || settings.allowCamera)),
  );
}

function createTrayMenu(): void {
  tray?.setContextMenu(
    Menu.buildFromTemplate([
      { label: `${t().tray.showHide}  (Ctrl+Alt+H)`, click: togglePill },
      { label: expanded ? t().tray.collapse : t().tray.expand, click: () => setExpanded(!expanded) },
      { label: t().tray.settings, click: openSettings },
      { type: "separator" },
      { label: t().tray.quit, click: () => app.quit() },
    ]),
  );
}

function createTray(): void {
  const icon = nativeImage.createFromPath(path.join(__dirname, "..", "assets", "icon.png")).resize({ width: 16, height: 16 });
  tray = new Tray(icon);
  tray.setToolTip("EZO");
  tray.on("click", togglePill);
  createTrayMenu();
}

const selfTestArg = process.argv.find((a) => a.startsWith("--self-test="));

if (!selfTestArg && !app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.whenReady().then(async () => {
    if (selfTestArg) {
      const folder = process.argv.find((a) => a.startsWith("--self-test-folder="))?.split("=")[1];
      const report = await runSelfTest({ actions, captureScreen, folder });
      writeFileSync(selfTestArg.split("=")[1]!, JSON.stringify(report, null, 2));
      app.exit(report.every((r) => r.ok || r.skipped || r.informational) ? 0 : 1);
      return;
    }
    const firstRun = !loadSettings();
    serveAppOrigin();
    allowOnlyAllowedMedia();
    registerIpc();
    createPill();
    createTray();
    registerShortcut();
    setInterval(() => void pollJarvis(), JARVIS_POLL_MS);
    setInterval(() => void refreshStatus(), STATUS_POLL_MS);
    void refreshStatus();
    // A new install, or a remote server without a token: the owner must see where to connect.
    if (firstRun || !settings.onboarded || (!readToken() && settings.apiUrl.startsWith("https:"))) openSettings();
  });
  app.on("before-quit", () => tell("visibility", false)); // release the microphone/camera first
  app.on("will-quit", () => globalShortcut.unregisterAll());
  app.on("window-all-closed", () => {
    // Stay in the tray; quitting is explicit.
  });
}
