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
    async chat(message: string, conversationId: string | null, projectId: string | null, channel: "text" | "voice") {
      const body = await json<{ conversation_id: string; message: Message }>(
        "/api/chat",
        post({ message, conversation_id: conversationId, project_id: projectId, channel }),
      );
      return { conversationId: body.conversation_id, reply: body.message };
    },
    async transcribe(audio: Blob): Promise<string> {
      const form = new FormData();
      form.append("audio", audio, "speech.webm");
      form.append("language", "uz");
      return (await json<{ text: string }>("/api/voice/transcribe", { method: "POST", body: form })).text.trim();
    },
    async speak(text: string): Promise<Blob> {
      return (await call("/api/voice/speak", post({ text: text.slice(0, 2000), language: "uz" }))).blob();
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
