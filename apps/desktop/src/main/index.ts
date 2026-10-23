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
  safeStorage,
  screen,
  session,
  shell,
  Tray,
} from "electron";
import { createActions } from "./actions";
import { createEzoClient, EzoApiError } from "./api";
import { createAssistant } from "./assistant";
import { findFiles, isInsideAllowed } from "./files";
import { runSelfTest } from "./selftest";
import { ALLOWED_SHORTCUTS, sanitizeSettings, type DesktopSettings } from "./settings";

const SETTINGS_FILE = () => path.join(app.getPath("userData"), "settings.json");
const TOKEN_FILE = () => path.join(app.getPath("userData"), "token.bin");
const MAX_AUDIO_BYTES = 10 * 1024 * 1024;

let pill: BrowserWindow | null = null;
let settingsWindow: BrowserWindow | null = null;
let tray: Tray | null = null;
let settings: DesktopSettings = sanitizeSettings({});

function loadSettings(): void {
  try {
    settings = sanitizeSettings(JSON.parse(readFileSync(SETTINGS_FILE(), "utf8")));
  } catch {
    settings = sanitizeSettings({});
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
  if (!source || source.thumbnail.isEmpty()) throw new Error("Ekran rasmini olib bo‘lmadi.");
  // Hide nothing, keep nothing: the PNG lives only in memory for this one request.
  return new Uint8Array(source.thumbnail.toPNG());
}

const assistant = createAssistant({
  settings: () => settings,
  client: () => createEzoClient(settings.apiUrl, readToken()),
  actions,
  findFiles,
  isInsideAllowed,
  confirm: async (message) => {
    const { response } = await dialog.showMessageBox({
      type: "question",
      buttons: ["Ruxsat beraman", "Bekor qilish"],
      defaultId: 1,
      cancelId: 1,
      title: "EZO",
      message,
    });
    return response === 0;
  },
  captureScreen,
  saveConversation: (id) => saveSettings({ ...settings, conversationId: id }),
});

interface TurnResponse {
  transcript?: string;
  reply?: string;
  acted?: boolean;
  audio?: { mimeType: string; data: Uint8Array };
  error?: string;
  notice?: string;
}

async function respond(text: string): Promise<TurnResponse> {
  const result = await assistant.handle(text);
  const out: TurnResponse = { transcript: text, reply: result.reply, acted: result.acted };
  if (settings.speakReplies) {
    try {
      out.audio = await createEzoClient(settings.apiUrl, readToken()).speak(result.reply);
    } catch (error) {
      out.notice = error instanceof EzoApiError ? error.message : "Javobni ovozda o‘qib bo‘lmadi.";
    }
  }
  return out;
}

function failure(error: unknown): TurnResponse {
  return { error: error instanceof EzoApiError ? error.message : `Xatolik: ${(error as Error).message}` };
}

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
  void pill.loadFile(path.join(__dirname, "pill.html"));
  pill.once("ready-to-show", () => pill?.showInactive());
}

function openSettings(): void {
  if (settingsWindow) return settingsWindow.focus();
  settingsWindow = new BrowserWindow({
    width: 560,
    height: 720,
    title: "EZO sozlamalari",
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, "preload-settings.js"),
      contextIsolation: true,
      sandbox: true,
      nodeIntegration: false,
    },
  });
  secureWindow(settingsWindow);
  void settingsWindow.loadFile(path.join(__dirname, "settings.html"));
  settingsWindow.on("closed", () => {
    settingsWindow = null;
  });
}

function registerShortcut(): void {
  globalShortcut.unregisterAll();
  const ok = globalShortcut.register(settings.shortcut, () => pill?.webContents.send("shortcut:toggle"));
  if (!ok) pill?.webContents.send("notice", `${settings.shortcut} tugmasi band. Sozlamalarda boshqasini tanlang.`);
}

function registerIpc(): void {
  ipcMain.handle("turn:audio", async (_event, audio: unknown, mimeType: unknown) => {
    if (!(audio instanceof ArrayBuffer) || audio.byteLength === 0 || audio.byteLength > MAX_AUDIO_BYTES) {
      return failure(new Error("Yozuv bo‘sh yoki juda katta."));
    }
    const type = typeof mimeType === "string" && /^audio\/[a-z0-9.+-]+(;.*)?$/i.test(mimeType) ? mimeType : "audio/webm";
    try {
      const text = await createEzoClient(settings.apiUrl, readToken()).transcribe(new Uint8Array(audio), type.split(";")[0]!);
      if (!text) return { error: "Hech narsa eshitilmadi. Qaytadan gapiring." };
      return await respond(text);
    } catch (error) {
      return failure(error);
    }
  });
  ipcMain.handle("turn:text", async (_event, text: unknown) => {
    if (typeof text !== "string" || !text.trim() || text.length > 4000) return failure(new Error("Matn noto‘g‘ri."));
    try {
      return await respond(text.trim());
    } catch (error) {
      return failure(error);
    }
  });
  ipcMain.on("pill:focusable", (_event, focusable: unknown) => {
    if (!pill || typeof focusable !== "boolean") return;
    pill.setFocusable(focusable);
    if (focusable) pill.focus();
    else pill.blur();
  });
  ipcMain.on("pill:height", (_event, height: unknown) => {
    if (!pill || typeof height !== "number") return;
    const [width] = pill.getSize();
    pill.setSize(width ?? 360, Math.max(72, Math.min(420, Math.round(height))));
  });
  ipcMain.on("settings:open", openSettings);

  ipcMain.handle("settings:get", () => ({
    settings,
    hasToken: Boolean(readToken()),
    secureStorage: safeStorage.isEncryptionAvailable(),
    shortcuts: ALLOWED_SHORTCUTS,
    platform: process.platform,
  }));
  ipcMain.handle("settings:save", (_event, next: unknown) => {
    const merged = sanitizeSettings({ ...settings, ...(next as object), allowedFolders: settings.allowedFolders });
    saveSettings(merged);
    registerShortcut();
    return settings;
  });
  ipcMain.handle("settings:token", (_event, token: unknown) =>
    writeToken(typeof token === "string" && token.trim() ? token.trim() : null),
  );
  ipcMain.handle("settings:add-folder", async () => {
    const result = await dialog.showOpenDialog({ properties: ["openDirectory"], title: "EZO qidira oladigan papka" });
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
  ipcMain.handle("settings:test", async () => {
    const client = createEzoClient(settings.apiUrl, readToken());
    try {
      await client.health();
      const me = await client.me();
      return { ok: true, message: `Ulandi: ${me.display_name ?? me.email ?? "EZO"}` };
    } catch (error) {
      return { ok: false, message: error instanceof EzoApiError ? error.message : String(error) };
    }
  });
}

function allowOnlyMicrophone(): void {
  session.defaultSession.setPermissionRequestHandler((contents, permission, callback, details) => {
    const fromPill = pill !== null && contents.id === pill.webContents.id;
    const audioOnly = permission === "media" && (details as { mediaTypes?: string[] }).mediaTypes?.every((t) => t === "audio");
    callback(Boolean(fromPill && audioOnly));
  });
  session.defaultSession.setPermissionCheckHandler((contents, permission) =>
    Boolean(pill && contents?.id === pill.webContents.id && permission === "media"),
  );
}

function createTray(): void {
  const icon = nativeImage.createFromPath(path.join(__dirname, "..", "assets", "icon.png")).resize({ width: 16, height: 16 });
  tray = new Tray(icon);
  tray.setToolTip("EZO");
  tray.setContextMenu(
    Menu.buildFromTemplate([
      { label: "Ko‘rsatish / yashirish", click: () => (pill?.isVisible() ? pill.hide() : pill?.showInactive()) },
      { label: "Sozlamalar", click: openSettings },
      { type: "separator" },
      { label: "Chiqish", click: () => app.quit() },
    ]),
  );
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
      app.exit(report.every((r) => r.ok || r.skipped) ? 0 : 1);
      return;
    }
    loadSettings();
    allowOnlyMicrophone();
    registerIpc();
    createPill();
    createTray();
    registerShortcut();
    if (!readToken() && settings.apiUrl.startsWith("https:")) openSettings();
  });
  app.on("will-quit", () => globalShortcut.unregisterAll());
  app.on("window-all-closed", () => {
    // Stay in the tray; quitting is explicit.
  });
}
