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
