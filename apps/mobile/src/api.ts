// The phone talks to the same EZO API, account and conversations as desktop and web.

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message);
  }
}

export interface Conversation {
  id: string;
  title: string;
  project_id: string | null;
  updated_at: string;
}
export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
}
export interface Project {
  id: string;
  name: string;
  description: string;
}
export interface Memory {
  id: string;
  content: string;
  category: string;
}

const UZ: Record<string, string> = {
  network: "EZO serveriga ulanib bo‘lmadi. Manzil, Wi-Fi/internet va serverning CORS sozlamasini tekshiring.",
  unauthorized: "Token noto‘g‘ri yoki kiritilmagan.",
  voice_not_configured: "Serverda nutqni aniqlash yoki ovoz chiqarish provayderi sozlanmagan.",
  vision_not_configured: "Serverda rasmni tushunadigan AI provayder sozlanmagan.",
  rate_limited: "Juda ko‘p so‘rov. Birozdan keyin urinib ko‘ring.",
};

export function createApi(baseUrl: string, token: string | null, fetchImpl: typeof fetch = fetch.bind(globalThis)) {
  const root = baseUrl.replace(/\/+$/, "");

  async function call(path: string, init: RequestInit = {}): Promise<Response> {
    const headers = new Headers(init.headers);
    if (token) headers.set("Authorization", `Bearer ${token}`);
    let response: Response;
    try {
      response = await fetchImpl(`${root}${path}`, { ...init, headers });
    } catch {
      throw new ApiError(0, "network", UZ.network!);
    }
    if (response.ok) return response;
    let code = `http_${response.status}`;
    let message = `So‘rov bajarilmadi (${response.status}).`;
    try {
      const body = (await response.json()) as { error?: { code?: string; message?: string } };
      if (body.error?.code) code = body.error.code;
      if (body.error?.message) message = body.error.message;
    } catch {
      // not JSON
    }
    if (response.status === 401) code = "unauthorized";
    if (response.status === 429) code = "rate_limited";
    throw new ApiError(response.status, code, UZ[code] ?? message);
  }
  const json = async <T>(path: string, init?: RequestInit) => (await call(path, init)).json() as Promise<T>;
  const post = (body: unknown): RequestInit => ({
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  return {
    me: () => json<{ email?: string; display_name?: string }>("/api/me"),
    conversations: () => json<Conversation[]>("/api/conversations?limit=50"),
    messages: (id: string) => json<Message[]>(`/api/conversations/${encodeURIComponent(id)}/messages`),
    projects: () => json<Project[]>("/api/projects"),
    memories: () => json<Memory[]>("/api/memories"),
    addMemory: (content: string) => json<Memory>("/api/memories", post({ content, category: "fact" })),
    /** `languageHint`: what the recogniser heard, used by the server when the words are ambiguous. */
    async chat(
      message: string,
      conversationId: string | null,
      projectId: string | null,
      channel: "text" | "voice",
      languageHint: Lang | null = null,
    ) {
      const body = await json<{ conversation_id: string; message: Message; language?: string }>(
        "/api/chat",
        post({
          message,
          conversation_id: conversationId,
          project_id: projectId,
          channel,
          ...(channel === "voice" && languageHint ? { language_hint: languageHint } : {}),
        }),
      );
      return { conversationId: body.conversation_id, reply: body.message, language: asLang(body.language) };
    },
    /** `language` null = EZO recognises Uzbek, English or Russian by itself. */
    async transcribe(audio: Blob, language: Lang | null = null): Promise<{ text: string; language: Lang | null }> {
      const form = new FormData();
      form.append("audio", audio, "speech.webm");
      if (language) form.append("language", language);
      const body = await json<{ text: string; language: string | null }>("/api/voice/transcribe", { method: "POST", body: form });
      return { text: body.text.trim(), language: asLang(body.language) ?? language };
    },
    async speak(text: string, language: Lang | null = "uz"): Promise<Blob> {
      return (await call("/api/voice/speak", post({ text: text.slice(0, 2000), language }))).blob();
    },
    /** Raw bytes to EZO Student; parsing happens only in the isolated worker. */
    async uploadStudent(name: string, bytes: Uint8Array): Promise<StudentJob> {
      return json<StudentJob>(`/api/student/uploads?filename=${encodeURIComponent(name)}`, {
        method: "POST",
        headers: { "Content-Type": "application/octet-stream" },
        body: new Blob([bytes.slice()], { type: "application/octet-stream" }),
      });
    },
    studentJob: (jobId: string) => json<StudentJob>(`/api/knowledge/document-jobs/${encodeURIComponent(jobId)}`),
    async studentSummary(documentId: string): Promise<{ text: string; citations: number }> {
      const body = await json<{ answer?: string; text?: string; citations?: unknown[] }>(
        `/api/student/documents/${encodeURIComponent(documentId)}/learn`,
        post({ kind: "summary", language: "uz" }),
      );
      return { text: body.answer ?? body.text ?? "", citations: body.citations?.length ?? 0 };
    },
    async describeImage(image: Blob, question: string): Promise<string> {
      const form = new FormData();
      form.append("image", image, image.type === "image/png" ? "photo.png" : "photo.jpg");
      form.append("question", question);
      form.append("language", "uz");
      return (await json<{ text: string }>("/api/vision/describe", { method: "POST", body: form })).text;
    },
  };
}

export type Api = ReturnType<typeof createApi>;

export interface StudentJob {
  id: string;
  document_id: string;
  state: "queued" | "running" | "completed" | "failed" | "cancelled";
  error_code: string | null;
  error_message: string | null;
}

export type Lang = "uz" | "en" | "ru";
export function asLang(value: string | null | undefined): Lang | null {
  return value === "uz" || value === "en" || value === "ru" ? value : null;
}
