// Pure status helpers for the popup. No chrome.* or network access here, so they are unit-testable.
//
// Canonical backend routes the extension may touch (apps/api/src/ezo_api): GET /api/health only.
// There is NO pairing, task, plan, execute, cancel or companion endpoint in the canonical
// backend, so the extension must never call one or display a state derived from one.

export const DEFAULT_API_BASE = "http://localhost:8000";
export const HEALTH_PATH = "/api/health";

/** Origin permission pattern for the backend, scoped to exactly one origin. */
export function originPattern(apiBase) {
  const url = new URL(apiBase);
  if (url.protocol !== "http:" && url.protocol !== "https:") throw new Error("unsupported_protocol");
  return `${url.protocol}//${url.hostname}/*`;
}

/**
 * @param {{ok: true, status: number} | {ok: false, reason: "permission_denied" | "unreachable" | "http_error", status?: number} | null} result
 * Reachability is NOT authentication, pairing or a device connection.
 */
export function describeBackend(result) {
  if (!result) return { state: "unknown", text: "Tekshirilmagan (backend holati noma'lum)" };
  if (result.ok) return { state: "reachable", text: `Backend javob berdi (HTTP ${result.status}). Bu ulanish yoki juftlash degani emas.` };
  if (result.reason === "permission_denied") return { state: "unknown", text: "Ruxsat berilmadi. Backend tekshirilmadi." };
  if (result.reason === "http_error") return { state: "error", text: `Backend xato qaytardi (HTTP ${result.status}).` };
  return { state: "unreachable", text: "Backendga yetib bo'lmadi." };
}

/** Honest, fixed copy for features the canonical backend does not provide. */
export const UNAVAILABLE = Object.freeze({
  pairing: "Qurilmani juftlash: mavjud emas (serverda juftlash API'si yo'q).",
  tasks: "Topshiriqlarni bajarish: mavjud emas (serverda reja/bajarish API'si yo'q).",
  telegram: "Telegramga yuborish: mavjud emas, hech narsa yuborilmaydi.",
});

/** Result of a user-initiated tab read. Only counts and the title are shown; nothing is sent anywhere. */
export function describePage(result) {
  if (!result || result.ok !== true) return { ok: false, text: "Sahifani o'qib bo'lmadi (maxsus yoki cheklangan sahifa bo'lishi mumkin)." };
  return { ok: true, title: result.title, origin: result.origin, selectionLength: result.selectionLength };
}
