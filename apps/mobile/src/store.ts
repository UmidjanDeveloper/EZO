// The token lives in Android Keystore-backed secure storage; non-secret preferences in
// localStorage. In a plain browser (development) the token falls back to sessionStorage.
import { Capacitor } from "@capacitor/core";
import { SecureStorage } from "@aparajita/capacitor-secure-storage";

const TOKEN_KEY = "ezo-api-token";
const PREFS_KEY = "ezo-mobile-prefs";

export interface Prefs {
  apiUrl: string;
  conversationId: string | null;
  projectId: string | null;
  speakReplies: boolean;
}

const DEFAULT_PREFS: Prefs = { apiUrl: "", conversationId: null, projectId: null, speakReplies: true };

export function loadPrefs(): Prefs {
  try {
    return { ...DEFAULT_PREFS, ...(JSON.parse(localStorage.getItem(PREFS_KEY) ?? "{}") as Partial<Prefs>) };
  } catch {
    return { ...DEFAULT_PREFS };
  }
}

export function savePrefs(prefs: Prefs): void {
  localStorage.setItem(PREFS_KEY, JSON.stringify(prefs));
}

const native = Capacitor.isNativePlatform();

export async function readToken(): Promise<string | null> {
  if (!native) return sessionStorage.getItem(TOKEN_KEY);
  const value = await SecureStorage.get(TOKEN_KEY).catch(() => null);
  return typeof value === "string" && value ? value : null;
}

export async function writeToken(token: string | null): Promise<void> {
  if (!native) {
    if (token) sessionStorage.setItem(TOKEN_KEY, token);
    else sessionStorage.removeItem(TOKEN_KEY);
    return;
  }
  if (token) await SecureStorage.set(TOKEN_KEY, token);
  else await SecureStorage.remove(TOKEN_KEY).catch(() => undefined);
}

/** Only HTTPS servers, or HTTP on a home/office LAN or this device while testing. */
export function normalizeApiUrl(raw: string): string | null {
  try {
    const url = new URL(raw.trim());
    const local = /^(localhost|127\.0\.0\.1|10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+)$/.test(url.hostname);
    if (url.protocol === "https:" || (url.protocol === "http:" && local)) return url.origin;
  } catch {
    // invalid
  }
  return null;
}
