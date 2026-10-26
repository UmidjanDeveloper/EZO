// The phone talks to the same EZO API, account and conversations as desktop and web.
import { format, strings, type Lang } from "./strings";

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
export interface ServerStatus {
  online: boolean;
  ai: boolean;
  voice: boolean;
  providers: string[];
}
export interface Artifact {
  id: string;
  title: string;
  type: string;
  updated_at: string;
  current_version: { version_number: number; filename: string; mime_type: string; file_size: number } | null;
}
export interface CueCard {
  id: string;
  task: string;
  points: string[];
}
export interface IeltsSession {
  id: string;
  status: string;
  ielts_part: number | null;
  current_prompt: string | null;
  answered_count: number;
  finished: boolean;
  feedback: string | null;
}
export interface IeltsAdvance {
  session_id: string;
  part: number;
  instruction: string;
  finished: boolean;
  feedback: string | null;
  explanation_uz: string | null;
  metrics: { words: number; unique_words: number; fillers: number; repeated: string[]; observations_uz: string[]; observations_en: string[]; heuristic_notice_uz: string; heuristic_notice_en: string } | null;
}
export interface JarvisStep {
  id: string;
  position: number;
  action: string;
  state: string;
  scope_sha256: string | null;
  output: { recipient?: string; telegram_name?: string; documents?: { filename: string }[] };
  error_message: string | null;
}
export interface JarvisTask {
  id: string;
  state: string;
  request_text: string;
  report: string;
  error_code: string | null;
  created_at: string;
  steps: JarvisStep[];
}
export interface JarvisCapabilities {
  device_features: Record<string, { available: boolean; missing?: string[] }>;
}

export interface ApiOptions {
  lang?: Lang;
  /** Cancels every request made through this client (the owner pressed stop). */
  signal?: AbortSignal;
}

export function createApi(baseUrl: string, token: string | null, fetchImpl: typeof fetch = fetch.bind(globalThis), options: ApiOptions = {}) {
  const root = baseUrl.replace(/\/+$/, "");
  const t = strings(options.lang).api;
  const known: Record<string, string> = {
    network: t.network,
    unauthorized: t.unauthorized,
    voice_not_configured: t.voice_not_configured,
    vision_not_configured: t.vision_not_configured,
    rate_limited: t.rate_limited,
    quota_exceeded: t.quota_exceeded,
  };

  async function call(path: string, init: RequestInit = {}): Promise<Response> {
    const headers = new Headers(init.headers);
    if (token) headers.set("Authorization", `Bearer ${token}`);
    let response: Response;
    try {
      response = await fetchImpl(`${root}${path}`, { ...init, headers, ...(options.signal ? { signal: options.signal } : {}) });
    } catch {
      if (options.signal?.aborted) throw new ApiError(0, "cancelled", t.cancelled);
      throw new ApiError(0, "network", t.network);
    }
    if (response.ok) return response;
    let code = `http_${response.status}`;
    let message = format(t.failed, { status: response.status });
    try {
      const body = (await response.json()) as { error?: { code?: string; message?: string } };
      if (body.error?.code) code = body.error.code;
      if (body.error?.message) message = body.error.message;
    } catch {
      // not JSON
    }
    if (response.status === 401) code = "unauthorized";
    if (response.status === 429 && code === "http_429") code = "rate_limited";
    throw new ApiError(response.status, code, known[code] ?? message);
  }
  const json = async <T>(path: string, init?: RequestInit) => (await call(path, init)).json() as Promise<T>;
  const post = (body: unknown): RequestInit => ({
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const id = encodeURIComponent;

  return {
    me: () => json<{ email?: string; display_name?: string }>("/api/me"),
    /** What the server can really do: reachable, an AI provider, voice. Never assumed. */
    async status(): Promise<ServerStatus> {
      const body = await json<{ offline_mode?: boolean; providers?: { name: string; configured: boolean; capabilities?: string[] }[] }>("/api/status");
      const configured = (body.providers ?? []).filter((p) => p.configured);
      return {
        online: true,
        ai: body.offline_mode === false && configured.length > 0,
        voice: configured.some((p) => (p.capabilities ?? []).some((c) => c.includes("speech") || c.includes("voice"))),
        providers: configured.map((p) => p.name),
      };
    },
    conversations: () => json<Conversation[]>("/api/conversations?limit=50"),
    messages: (conversationId: string) => json<Message[]>(`/api/conversations/${id(conversationId)}/messages`),
    projects: () => json<Project[]>("/api/projects"),
    createProject: (name: string) => json<Project>("/api/projects", post({ name })),
    memories: () => json<Memory[]>("/api/memories"),
    addMemory: (content: string) => json<Memory>("/api/memories", post({ content, category: "fact" })),
    deleteMemory: async (memoryId: string) => {
      await call(`/api/memories/${id(memoryId)}`, { method: "DELETE" });
    },
    /** `languageHint`: what the recogniser heard, used by the server when the words are ambiguous. */
    async chat(message: string, conversationId: string | null, projectId: string | null, channel: "text" | "voice", languageHint: Lang | null = null) {
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
    studentJob: (jobId: string) => json<StudentJob>(`/api/knowledge/document-jobs/${id(jobId)}`),
    async studentSummary(documentId: string, language: Lang = "uz"): Promise<{ text: string; citations: number }> {
      const body = await json<{ answer?: string; text?: string; citations?: unknown[] }>(
        `/api/student/documents/${id(documentId)}/learn`,
        post({ kind: "summary", language }),
      );
      return { text: body.answer ?? body.text ?? "", citations: body.citations?.length ?? 0 };
    },
    async describeImage(image: Blob, question: string, language: Lang = "uz"): Promise<string> {
      const form = new FormData();
      form.append("image", image, image.type === "image/png" ? "photo.png" : "photo.jpg");
      form.append("question", question);
      form.append("language", language);
      return (await json<{ text: string }>("/api/vision/describe", { method: "POST", body: form })).text;
    },

    // --- generated files (Office, presentations, PDFs) ---
    artifacts: () => json<Artifact[]>("/api/artifacts?limit=50"),
    /** The current version's real bytes, as the server stores them. */
    downloadArtifact: async (artifactId: string): Promise<{ blob: Blob; filename: string }> => {
      const response = await call(`/api/artifacts/${id(artifactId)}/download`);
      const disposition = response.headers.get("Content-Disposition") ?? "";
      const match = /filename\*=UTF-8''([^;]+)|filename="?([^";]+)"?/i.exec(disposition);
      const filename = decodeURIComponent(match?.[1] ?? match?.[2] ?? "ezo-file");
      return { blob: await response.blob(), filename };
    },

    // --- IELTS speaking practice ---
    cueCards: () => json<CueCard[]>("/api/ielts/cue-cards"),
    startIelts: (cueCard: string | null) => json<IeltsSession>("/api/ielts/sessions", post({ cue_card: cueCard })),
    ieltsSession: (sessionId: string) => json<IeltsSession>(`/api/ielts/sessions/${id(sessionId)}`),
    ieltsAdvance: (sessionId: string, answer: string, speechSeconds: number | null) =>
      json<IeltsAdvance>(`/api/ielts/sessions/${id(sessionId)}/advance`, post({ answer, speech_seconds: speechSeconds })),
    ieltsHistory: () => json<unknown[]>("/api/ielts/history"),

    // --- JARVIS governed tasks (approvals and cancellation from the phone) ---
    jarvisTasks: () => json<JarvisTask[]>("/api/jarvis/tasks"),
    jarvisTask: (taskId: string) => json<JarvisTask>(`/api/jarvis/tasks/${id(taskId)}`),
    jarvisCapabilities: () => json<JarvisCapabilities>("/api/jarvis/capabilities"),
    createJarvisTask: (text: string, language: Lang) =>
      json<JarvisTask>("/api/jarvis/tasks", post({ text, language, idempotency_key: `mobile-${crypto.randomUUID()}` })),
    decideJarvisStep: (taskId: string, stepId: string, scope: string, approve: boolean) =>
      json<JarvisTask>(`/api/jarvis/tasks/${id(taskId)}/steps/${id(stepId)}/decision`, post({ scope_sha256: scope, approve })),
    cancelJarvisTask: (taskId: string) => json<JarvisTask>(`/api/jarvis/tasks/${id(taskId)}/cancel`, { method: "POST" }),
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

export type { Lang };
export function asLang(value: string | null | undefined): Lang | null {
  return value === "uz" || value === "en" || value === "ru" ? value : null;
}
