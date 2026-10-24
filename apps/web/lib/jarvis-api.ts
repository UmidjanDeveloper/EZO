import { apiUrl, storedToken } from "./api";
import {
  JARVIS_ENDPOINTS,
  parseCapabilities,
  parsePercentageResult,
  type Capabilities,
  type PercentageRequest,
  type PercentageResult,
} from "./jarvis-contract";

export type JarvisFetch = typeof fetch;

export class JarvisApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
  ) {
    super(code);
    this.name = "JarvisApiError";
  }
}

function headers(json: boolean): Record<string, string> {
  const token = storedToken.get().trim();
  return {
    Accept: "application/json",
    ...(json ? { "Content-Type": "application/json" } : {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

async function errorCode(res: Response): Promise<string> {
  try {
    const body: unknown = await res.json();
    // The API reports errors as {"error": {"code", "message"}} (older routes: "detail").
    if (typeof body === "object" && body !== null && "error" in body) {
      const error = (body as { error: unknown }).error;
      if (typeof error === "object" && error !== null && "code" in error) {
        const code = (error as { code: unknown }).code;
        if (typeof code === "string") return code;
      }
    }
    if (typeof body === "object" && body !== null && "detail" in body) {
      const detail = (body as { detail: unknown }).detail;
      if (typeof detail === "string") return detail;
      if (typeof detail === "object" && detail !== null && "code" in detail) {
        const code = (detail as { code: unknown }).code;
        if (typeof code === "string") return code;
      }
    }
  } catch {
    // Non-JSON error body: fall through to the status code.
  }
  return `http_${res.status}`;
}

export async function fetchCapabilities(fetchImpl: JarvisFetch = fetch): Promise<Capabilities> {
  const res = await fetchImpl(`${apiUrl()}${JARVIS_ENDPOINTS.capabilities}`, {
    headers: headers(false),
  });
  if (!res.ok) throw new JarvisApiError(res.status, await errorCode(res));
  const parsed = parseCapabilities(await res.json());
  if (!parsed) throw new JarvisApiError(res.status, "unexpected_response_shape");
  return parsed;
}

export async function postPercentages(
  body: PercentageRequest,
  fetchImpl: JarvisFetch = fetch,
): Promise<PercentageResult> {
  const res = await fetchImpl(`${apiUrl()}${JARVIS_ENDPOINTS.percentages}`, {
    method: "POST",
    headers: headers(true),
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new JarvisApiError(res.status, await errorCode(res));
  const parsed = parsePercentageResult(await res.json());
  if (!parsed) throw new JarvisApiError(res.status, "unexpected_response_shape");
  return parsed;
}

// --- governed tasks, devices and recipients ---------------------------------------------

export interface JarvisErrorBody {
  code: string;
  message: string;
}

export class JarvisCallError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "JarvisCallError";
  }
}

const JARVIS_ROUTE = /^\/api\/jarvis\/[A-Za-z0-9_\-/]+$/;

/** `path` is the full literal route at each call site, so `jarvis-contract.test.ts` can
 * check every referenced route against the backend source. */
export async function jarvisCall<T>(path: string, init: { method?: string; body?: unknown } = {}, fetchImpl: JarvisFetch = fetch): Promise<T> {
  if (!JARVIS_ROUTE.test(path)) throw new JarvisCallError(0, "invalid_route", "Invalid JARVIS route.");
  const res = await fetchImpl(`${apiUrl()}${path}`, {
    method: init.method ?? "GET",
    headers: headers(init.body !== undefined),
    body: init.body === undefined ? undefined : JSON.stringify(init.body),
  });
  const text = await res.text();
  let body: unknown = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = null;
  }
  if (!res.ok) {
    const error = (body as { error?: Partial<JarvisErrorBody> } | null)?.error;
    throw new JarvisCallError(res.status, error?.code ?? `http_${res.status}`, error?.message ?? `HTTP ${res.status}`);
  }
  return body as T;
}

export interface JarvisDevice {
  id: string;
  name: string;
  platform: string;
  status: "pending" | "paired" | "revoked";
  last_seen_at: string | null;
}

export interface JarvisRecipient {
  id: string;
  label: string;
  status: "pending" | "verified" | "revoked";
  telegram_name: string | null;
}

export interface JarvisStep {
  id: string;
  position: number;
  action: string;
  state: string;
  output: Record<string, unknown>;
  receipt: Record<string, unknown>;
  scope_sha256: string | null;
  error_code: string | null;
  error_message: string | null;
}

export interface JarvisTask {
  id: string;
  state: "queued" | "awaiting_authorization" | "running" | "completed" | "failed" | "cancelled";
  request_text: string;
  report: string;
  error_code: string | null;
  created_at: string | null;
  steps: JarvisStep[];
}
