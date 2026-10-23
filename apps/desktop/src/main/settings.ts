/**
 * Local settings and revocable permissions. Everything starts DISABLED: the owner turns
 * on each capability (and adds each folder) explicitly in the settings window.
 */
import type { AppId } from "./intents";

export interface DesktopSettings {
  apiUrl: string;
  allowedFolders: string[];
  apps: Record<AppId, boolean>;
  allowTyping: boolean;
  allowScreen: boolean;
  allowVolume: boolean;
  speakReplies: boolean;
  shortcut: string;
  conversationId: string | null;
}

export const DEFAULT_SETTINGS: DesktopSettings = {
  apiUrl: "http://localhost:8000",
  allowedFolders: [],
  apps: { calculator: false, notepad: false, paint: false, explorer: false },
  allowTyping: false,
  allowScreen: false,
  allowVolume: false,
  speakReplies: true,
  shortcut: "Control+Alt+Space",
  conversationId: null,
};

const SHORTCUTS = new Set(["Control+Alt+Space", "Control+Shift+Space", "Alt+Space", "Control+Alt+E"]);

/** Accepts only well-formed values; anything unexpected falls back to the safe default. */
export function sanitizeSettings(raw: unknown): DesktopSettings {
  const input = (raw && typeof raw === "object" ? raw : {}) as Record<string, unknown>;
  const bool = (key: keyof DesktopSettings, fallback: boolean) =>
    typeof input[key] === "boolean" ? (input[key] as boolean) : fallback;
  const apps = (input.apps && typeof input.apps === "object" ? input.apps : {}) as Record<string, unknown>;
  let apiUrl = DEFAULT_SETTINGS.apiUrl;
  if (typeof input.apiUrl === "string") {
    try {
      const url = new URL(input.apiUrl);
      const loopback = ["localhost", "127.0.0.1", "[::1]"].includes(url.hostname);
      const privateLan = /^(10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)/.test(url.hostname);
      if (url.protocol === "https:" || (url.protocol === "http:" && (loopback || privateLan))) {
        apiUrl = url.origin;
      }
    } catch {
      // keep default
    }
  }
  const folders = Array.isArray(input.allowedFolders)
    ? input.allowedFolders.filter((f): f is string => typeof f === "string" && f.length > 2).slice(0, 20)
    : [];
  return {
    apiUrl,
    allowedFolders: [...new Set(folders)],
    apps: {
      calculator: apps.calculator === true,
      notepad: apps.notepad === true,
      paint: apps.paint === true,
      explorer: apps.explorer === true,
    },
    allowTyping: bool("allowTyping", false),
    allowScreen: bool("allowScreen", false),
    allowVolume: bool("allowVolume", false),
    speakReplies: bool("speakReplies", true),
    shortcut: typeof input.shortcut === "string" && SHORTCUTS.has(input.shortcut) ? input.shortcut : DEFAULT_SETTINGS.shortcut,
    conversationId:
      typeof input.conversationId === "string" && /^[0-9a-f-]{36}$/.test(input.conversationId)
        ? input.conversationId
        : null,
  };
}

export const ALLOWED_SHORTCUTS = [...SHORTCUTS];
