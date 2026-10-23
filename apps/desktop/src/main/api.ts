/**
 * The desktop app's only link to EZO: the same HTTP API, account and conversations as
 * the web and mobile apps. Runs in the main process, so the owner token never reaches
 * a renderer, a webpage or a log line.
 */

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
}

type Fetch = typeof fetch;

const UZ_MESSAGES: Record<string, string> = {
  network: "EZO serveriga ulanib bo‘lmadi. Server manzilini va internetni tekshiring.",
  unauthorized: "Kirish tokeni noto‘g‘ri yoki yo‘q. Sozlamalarda tokenni kiriting.",
  voice_not_configured: "Serverda nutqni aniqlash/ovoz chiqarish provayderi sozlanmagan.",
  vision_not_configured: "Serverda rasmni tushunadigan AI provayder sozlanmagan.",
  rate_limited: "Juda ko‘p so‘rov. Birozdan keyin urinib ko‘ring.",
};

export function createEzoClient(baseUrl: string, token: string | null, fetchImpl: Fetch = fetch) {
  const root = baseUrl.replace(/\/+$/, "");

  async function request(path: string, init: RequestInit = {}, timeoutMs = 90_000): Promise<Response> {
    const headers = new Headers(init.headers);
    if (token) headers.set("Authorization", `Bearer ${token}`);
    let response: Response;
    try {
      response = await fetchImpl(`${root}${path}`, { ...init, headers, signal: AbortSignal.timeout(timeoutMs) });
    } catch {
      throw new EzoApiError(0, "network", UZ_MESSAGES.network!);
    }
    if (response.ok) return response;
    let code = `http_${response.status}`;
    let message = `So‘rov bajarilmadi (${response.status}).`;
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
    throw new EzoApiError(response.status, code, UZ_MESSAGES[code] ?? message);
  }

  return {
    async health(): Promise<boolean> {
      await request("/api/health", {}, 10_000);
      return true;
    },

    async me(): Promise<{ email?: string; display_name?: string }> {
      return (await request("/api/me", {}, 15_000)).json() as Promise<{ email?: string; display_name?: string }>;
    },

    async transcribe(audio: Uint8Array, mimeType: string, language: "uz" | "en" | "ru" = "uz"): Promise<string> {
      const form = new FormData();
      form.append("audio", new Blob([audio.slice()], { type: mimeType }), "speech.webm");
      form.append("language", language);
      const body = (await (await request("/api/voice/transcribe", { method: "POST", body: form })).json()) as {
        text: string;
      };
      return body.text.trim();
    },

    async chat(message: string, conversationId: string | null): Promise<ChatReply> {
      const response = await request(
        "/api/chat",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message, conversation_id: conversationId, channel: "voice" }),
        },
        180_000,
      );
      const body = (await response.json()) as { conversation_id: string; message: { content: string } };
      return { conversationId: body.conversation_id, text: body.message.content };
    },

    async speak(text: string, language: "uz" | "en" | "ru" = "uz"): Promise<{ mimeType: string; data: Uint8Array }> {
      const response = await request("/api/voice/speak", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: text.slice(0, 2000), language }),
      });
      return {
        mimeType: response.headers.get("content-type") ?? "audio/mpeg",
        data: new Uint8Array(await response.arrayBuffer()),
      };
    },

    async describeImage(png: Uint8Array, question: string): Promise<string> {
      const form = new FormData();
      form.append("image", new Blob([png.slice()], { type: "image/png" }), "screen.png");
      form.append("question", question.slice(0, 1000));
      form.append("language", "uz");
      const body = (await (await request("/api/vision/describe", { method: "POST", body: form }, 120_000)).json()) as {
        text: string;
      };
      return body.text;
    },
  };
}

export type EzoClient = ReturnType<typeof createEzoClient>;
