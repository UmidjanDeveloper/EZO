/**
 * The desktop app's only link to EZO: the same HTTP API, account and conversations as
 * the web and mobile apps. Runs in the main process, so the owner token never reaches
 * a renderer, a webpage or a log line.
 */
import type { Lang } from "./replies";
import { format, strings } from "./strings";

export class EzoApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message);
  }
}

export interface ChatReply {
  conversationId: string;
  text: string;
  /** The reply's language as the server decided it (uz, en or ru). */
  language: Lang | null;
}

export type { Lang };
const asLang = (value: string | null | undefined): Lang | null =>
  value === "uz" || value === "en" || value === "ru" ? value : null;

type Fetch = typeof fetch;

export interface ClientOptions {
  /** Language of the error messages shown to the owner. */
  lang?: Lang;
  /** Cancels every request made through this client (the owner pressed stop). */
  signal?: AbortSignal;
}

export function createEzoClient(baseUrl: string, token: string | null, fetchImpl: Fetch = fetch, options: ClientOptions = {}) {
  const root = baseUrl.replace(/\/+$/, "");
  const t = strings(options.lang ?? "uz").api;
  const known: Record<string, string> = {
    network: t.network,
    unauthorized: t.unauthorized,
    voice_not_configured: t.voice_not_configured,
    vision_not_configured: t.vision_not_configured,
    rate_limited: t.rate_limited,
  };

  async function request(path: string, init: RequestInit = {}, timeoutMs = 90_000): Promise<Response> {
    const headers = new Headers(init.headers);
    if (token) headers.set("Authorization", `Bearer ${token}`);
    const signals = [AbortSignal.timeout(timeoutMs), ...(options.signal ? [options.signal] : [])];
    let response: Response;
    try {
      response = await fetchImpl(`${root}${path}`, { ...init, headers, signal: AbortSignal.any(signals) });
    } catch {
      if (options.signal?.aborted) throw new EzoApiError(0, "cancelled", t.cancelled);
      throw new EzoApiError(0, "network", t.network);
    }
    if (response.ok) return response;
    let code = `http_${response.status}`;
    let message = format(t.failed, { status: response.status });
    try {
      const body = (await response.json()) as { error?: { code?: string; message?: string }; detail?: unknown };
      const error = body.error ?? (typeof body.detail === "object" ? (body.detail as { code?: string; message?: string }) : undefined);
      if (error?.code) code = error.code;
      if (error?.message) message = error.message;
    } catch {
      // non-JSON error body
    }
    if (response.status === 401) code = "unauthorized";
    if (response.status === 429) code = "rate_limited";
    throw new EzoApiError(response.status, code, known[code] ?? message);
  }

  return {
    async health(): Promise<boolean> {
      await request("/api/health", {}, 10_000);
      return true;
    },

    /** What the server can really do right now: an AI provider, voice, vision. */
    async status(): Promise<ServerStatus> {
      const body = (await (await request("/api/status", {}, 10_000)).json()) as {
        offline_mode?: boolean;
        providers?: { name: string; configured: boolean; capabilities?: string[] }[];
        version?: string;
      };
      const configured = (body.providers ?? []).filter((p) => p.configured);
      return {
        ai: body.offline_mode === false && configured.length > 0,
        voice: configured.some((p) => (p.capabilities ?? []).some((c) => c.includes("speech") || c.includes("voice"))),
        providers: configured.map((p) => p.name),
        version: body.version ?? "",
      };
    },

    async conversations(limit = 20): Promise<{ id: string; title: string; updated_at: string }[]> {
      return (await request(`/api/conversations?limit=${limit}`, {}, 15_000)).json() as Promise<
        { id: string; title: string; updated_at: string }[]
      >;
    },

    async messages(conversationId: string, limit = 12): Promise<{ role: string; content: string; created_at: string }[]> {
      const body = (await (
        await request(`/api/conversations/${encodeURIComponent(conversationId)}/messages?limit=${limit}`, {}, 15_000)
      ).json()) as { role: string; content: string; created_at: string }[];
      return Array.isArray(body) ? body : [];
    },

    async me(): Promise<{ email?: string; display_name?: string }> {
      return (await request("/api/me", {}, 15_000)).json() as Promise<{ email?: string; display_name?: string }>;
    },

    /** `language` null: the server recognises Uzbek, English or Russian and reports which. */
    async transcribe(audio: Uint8Array, mimeType: string, language: Lang | null = null): Promise<{ text: string; language: Lang | null }> {
      const form = new FormData();
      form.append("audio", new Blob([audio.slice()], { type: mimeType }), "speech.webm");
      if (language) form.append("language", language);
      const body = (await (await request("/api/voice/transcribe", { method: "POST", body: form })).json()) as {
        text: string;
        language?: string | null;
      };
      return { text: body.text.trim(), language: asLang(body.language) ?? language };
    },

    async chat(message: string, conversationId: string | null, languageHint: Lang | null = null): Promise<ChatReply> {
      const response = await request(
        "/api/chat",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            message,
            conversation_id: conversationId,
            channel: "voice",
            ...(languageHint ? { language_hint: languageHint } : {}),
          }),
        },
        180_000,
      );
      const body = (await response.json()) as { conversation_id: string; message: { content: string }; language?: string };
      return { conversationId: body.conversation_id, text: body.message.content, language: asLang(body.language) };
    },

    async speak(text: string, language: Lang = "uz"): Promise<{ mimeType: string; data: Uint8Array; provider: string | null }> {
      const response = await request("/api/voice/speak", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: text.slice(0, 2000), language }),
      });
      return {
        mimeType: response.headers.get("content-type") ?? "audio/mpeg",
        data: new Uint8Array(await response.arrayBuffer()),
        provider: response.headers.get("x-ezo-voice-provider"),
      };
    },

    async describeImage(png: Uint8Array, question: string, language: Lang = "uz"): Promise<string> {
      const form = new FormData();
      form.append("image", new Blob([png.slice()], { type: "image/png" }), "screen.png");
      form.append("question", question.slice(0, 1000));
      form.append("language", language);
      const body = (await (await request("/api/vision/describe", { method: "POST", body: form }, 120_000)).json()) as {
        text: string;
      };
      return body.text;
    },

    // --- JARVIS device companion (pairing, fixed work items, signed results) ---

    async requestPairing(body: Record<string, unknown>): Promise<{ device: { id: string; status: string }; code: string }> {
      const response = await request(
        "/api/jarvis/devices/pairing",
        { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) },
        20_000,
      );
      return response.json() as Promise<{ device: { id: string; status: string }; code: string }>;
    },

    async devices(): Promise<{ id: string; status: string; name: string }[]> {
      return (await request("/api/jarvis/devices", {}, 15_000)).json() as Promise<{ id: string; status: string; name: string }[]>;
    },

    async createJarvisTask(text: string, language: Lang = "uz"): Promise<JarvisTaskView> {
      const response = await request(
        "/api/jarvis/tasks",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text, language, idempotency_key: `desktop-${crypto.randomUUID()}` }),
        },
        30_000,
      );
      return response.json() as Promise<JarvisTaskView>;
    },

    async jarvisTask(taskId: string): Promise<JarvisTaskView> {
      return (await request(`/api/jarvis/tasks/${encodeURIComponent(taskId)}`, {}, 20_000)).json() as Promise<JarvisTaskView>;
    },

    async decideJarvisStep(taskId: string, stepId: string, scope: string, approve: boolean): Promise<JarvisTaskView> {
      const response = await request(
        `/api/jarvis/tasks/${encodeURIComponent(taskId)}/steps/${encodeURIComponent(stepId)}/decision`,
        { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ scope_sha256: scope, approve }) },
        60_000,
      );
      return response.json() as Promise<JarvisTaskView>;
    },

    async cancelJarvisTask(taskId: string): Promise<JarvisTaskView> {
      return (await request(`/api/jarvis/tasks/${encodeURIComponent(taskId)}/cancel`, { method: "POST" }, 20_000)).json() as Promise<JarvisTaskView>;
    },

    async revokeDevice(deviceId: string): Promise<void> {
      await request(`/api/jarvis/devices/${encodeURIComponent(deviceId)}`, { method: "DELETE" }, 15_000);
    },

    async deviceWork(deviceId: string): Promise<unknown[]> {
      const body = await (await request(`/api/jarvis/devices/${encodeURIComponent(deviceId)}/work`, {}, 20_000)).json();
      return Array.isArray(body) ? body : [];
    },

    async submitDeviceResult(deviceId: string, result: unknown): Promise<{ state: string; report: string }> {
      const response = await request(
        `/api/jarvis/devices/${encodeURIComponent(deviceId)}/results`,
        { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(result) },
        60_000,
      );
      return response.json() as Promise<{ state: string; report: string }>;
    },
  };
}

export type EzoClient = ReturnType<typeof createEzoClient>;

export interface ServerStatus {
  /** An AI provider is configured and the server is not in offline mode. */
  ai: boolean;
  /** Some configured provider offers speech. */
  voice: boolean;
  providers: string[];
  version: string;
}

export interface JarvisTaskView {
  id: string;
  state: string;
  report: string;
  steps: {
    id: string;
    action: string;
    state: string;
    scope_sha256: string | null;
    output: { recipient?: string; telegram_name?: string; documents?: { filename: string; sha256: string }[] };
  }[];
}
