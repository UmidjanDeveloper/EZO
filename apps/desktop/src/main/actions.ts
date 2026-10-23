/**
 * The complete list of things EZO may do on this computer. Each action has a fixed
 * implementation: fixed executables and fixed PowerShell snippets, run without a shell.
 * User text (dictation) only ever travels through the clipboard, never into a command
 * line. Model replies never reach this module.
 */
import type { AppId, VolumeChange } from "./intents";

export interface ActionDeps {
  platform: NodeJS.Platform;
  /** execFile-style runner: no shell, arguments passed as an array. */
  run(file: string, args: readonly string[]): Promise<void>;
  clipboard: { readText(): string | Promise<string>; writeText(text: string): void | Promise<void> };
  openPath(target: string): Promise<string>; // Electron shell.openPath: "" on success
  sleep(ms: number): Promise<void>;
}

export class UnsupportedAction extends Error {}

const WINDOWS_APPS: Record<AppId, string> = {
  calculator: "calc.exe",
  notepad: "notepad.exe",
  paint: "mspaint.exe",
  explorer: "explorer.exe",
};

/** Virtual-key characters understood by WScript.Shell SendKeys for the media keys. */
const VOLUME_KEYS: Record<VolumeChange, { key: number; times: number }> = {
  up: { key: 175, times: 5 }, // each press is 2 %
  down: { key: 174, times: 5 },
  mute: { key: 173, times: 1 },
};

const POWERSHELL = "powershell.exe";
const PS_ARGS = ["-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command"] as const;

export const APP_NAMES_UZ: Record<AppId, string> = {
  calculator: "Kalkulyator",
  notepad: "Bloknot",
  paint: "Paint",
  explorer: "Fayl menejeri",
};

export function createActions(deps: ActionDeps) {
  const windowsOnly = () => {
    if (deps.platform !== "win32") throw new UnsupportedAction("Bu amal hozircha faqat Windows’da ishlaydi.");
  };

  return {
    async openApp(app: AppId): Promise<void> {
      windowsOnly();
      await deps.run(WINDOWS_APPS[app], []);
    },

    async changeVolume(change: VolumeChange): Promise<void> {
      windowsOnly();
      const { key, times } = VOLUME_KEYS[change];
      const script = `$s=New-Object -ComObject WScript.Shell; 1..${times} | ForEach-Object { $s.SendKeys([char]${key}) }`;
      await deps.run(POWERSHELL, [...PS_ARGS, script]);
    },

    /** Pastes text into whichever window has focus, then restores the clipboard. */
    async typeText(text: string): Promise<void> {
      windowsOnly();
      if (!text || text.length > 4000) throw new UnsupportedAction("Matn bo‘sh yoki juda uzun.");
      const previous = await deps.clipboard.readText();
      await deps.clipboard.writeText(text);
      try {
        await deps.run(POWERSHELL, [...PS_ARGS, "$s=New-Object -ComObject WScript.Shell; $s.SendKeys('^v')"]);
        await deps.sleep(400);
      } finally {
        await deps.clipboard.writeText(previous);
      }
    },

    async openFile(target: string): Promise<void> {
      const error = await deps.openPath(target);
      if (error) throw new UnsupportedAction(`Faylni ochib bo‘lmadi: ${error}`);
    },
  };
}

export type Actions = ReturnType<typeof createActions>;
