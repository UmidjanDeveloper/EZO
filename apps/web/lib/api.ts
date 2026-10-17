import { createApiClient } from "@ezo/shared";
import { createStoredValue } from "./stored-value";

/** Optional API token (EZO_AUTH_MODE=token), kept only in this browser. */
export const storedToken = createStoredValue("ezo-api-token", "", (value): value is string => typeof value === "string");

declare global {
  interface Window {
    /** Set at runtime by /ezo-config (from the EZO_API_URL server environment variable). */
    __EZO_API_URL__?: string;
  }
}

/** Where the browser finds the EZO API. Runtime config wins over the build-time default. */
export function apiUrl(): string {
  if (typeof window !== "undefined" && window.__EZO_API_URL__) return window.__EZO_API_URL__;
  return process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
}

export const api = createApiClient({
  baseUrl: apiUrl,
  getToken: () => storedToken.get().trim() || null,
});
