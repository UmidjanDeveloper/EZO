/**
 * Typed client for the EZO API. Works in the browser and in Node.
 */

import { SseParser } from "./sse";
import type {
  AgentRun,
  ChatRequestBody,
  ChatStreamEvent,
  Conversation,
  KnowledgeDocument,
  KnowledgeDocumentDetail,
  KnowledgeOverview,
  KnowledgeSearchResult,
  KnowledgeUploadResult,
  Memory,
  MemoryCategory,
  Message,
  Preferences,
  Project,
  SystemStatus,
  User,
  VoiceStatus,
  VoiceTranscript,
} from "./types";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly hint?: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export interface ApiClientOptions {
  /** API base URL, or a function returning it (resolved on every request). */
  baseUrl: string | (() => string);
  /** Returns the API token when EZO runs with EZO_AUTH_MODE=token. */
  getToken?: () => string | null | undefined;
  fetchImpl?: typeof fetch;
}

const STREAM_EVENTS = new Set(["meta", "activity", "delta", "done", "error"]);

export function createApiClient(options: ApiClientOptions) {
  const baseUrl = () =>
    (typeof options.baseUrl === "function" ? options.baseUrl() : options.baseUrl).replace(/\/+$/, "");
  const doFetch: typeof fetch = options.fetchImpl ?? ((...args) => fetch(...args));

  function headers(json: boolean): HeadersInit {
    const result: Record<string, string> = {};
    if (json) result["Content-Type"] = "application/json";
    const token = options.getToken?.();
    if (token) result["Authorization"] = `Bearer ${token}`;
    return result;
  }

  async function send(path: string, init: RequestInit = {}): Promise<Response> {
    const base = baseUrl();
    let response: Response;
    try {
      response = await doFetch(`${base}${path}`, {
        ...init,
        // FormData sets its own multipart Content-Type (with boundary).
        headers: {
          ...headers(init.body !== undefined && !(init.body instanceof FormData)),
          ...(init.headers ?? {}),
        },
      });
    } catch {
      throw new ApiError(
        0,
        "network_error",
        "Cannot reach the EZO API. Is it running?",
        `Tried ${base}. Start it with: python scripts/ezo.py dev`,
      );
    }
    if (!response.ok) throw await toApiError(response);
    return response;
  }

  async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const response = await send(path, init);
    if (response.status === 204) return undefined as T;
    return (await response.json()) as T;
  }

  const json = (body: unknown): RequestInit => ({ body: JSON.stringify(body) });

  return {
    get baseUrl() {
      return baseUrl();
    },

    health: () => request<{ status: string; database: string; version: string }>("/api/health"),
    status: () => request<SystemStatus>("/api/status"),
    me: () => request<User>("/api/me"),
    updatePreferences: (prefs: Partial<Preferences>) =>
      request<User>("/api/me/preferences", { method: "PATCH", ...json(prefs) }),

    listConversations: (projectId?: string) =>
      request<Conversation[]>(
        `/api/conversations${projectId ? `?project_id=${encodeURIComponent(projectId)}` : ""}`,
      ),
    getConversation: (id: string) => request<Conversation>(`/api/conversations/${id}`),
    listMessages: (id: string) => request<Message[]>(`/api/conversations/${id}/messages`),
    renameConversation: (id: string, title: string) =>
      request<Conversation>(`/api/conversations/${id}`, { method: "PATCH", ...json({ title }) }),
    deleteConversation: (id: string) =>
      request<void>(`/api/conversations/${id}`, { method: "DELETE" }),

    listProjects: () => request<Project[]>("/api/projects"),
    getProject: (id: string) => request<Project>(`/api/projects/${id}`),
    createProject: (name: string, description = "") =>
      request<Project>("/api/projects", { method: "POST", ...json({ name, description }) }),
    updateProject: (id: string, changes: Partial<Pick<Project, "name" | "description" | "status">>) =>
      request<Project>(`/api/projects/${id}`, { method: "PATCH", ...json(changes) }),
    deleteProject: (id: string) => request<void>(`/api/projects/${id}`, { method: "DELETE" }),

    listMemories: (filter: { memoryType?: "profile" | "project"; projectId?: string } = {}) => {
      const params = new URLSearchParams();
      if (filter.memoryType) params.set("memory_type", filter.memoryType);
      if (filter.projectId) params.set("project_id", filter.projectId);
      const query = params.toString();
      return request<Memory[]>(`/api/memories${query ? `?${query}` : ""}`);
    },
    createMemory: (memory: {
      content: string;
      category?: MemoryCategory;
      memory_type?: "profile" | "project";
      project_id?: string | null;
      importance?: number;
    }) => request<Memory>("/api/memories", { method: "POST", ...json(memory) }),
    updateMemory: (id: string, changes: { content?: string; importance?: number }) =>
      request<Memory>(`/api/memories/${id}`, { method: "PATCH", ...json(changes) }),
    deleteMemory: (id: string) => request<void>(`/api/memories/${id}`, { method: "DELETE" }),
    deleteAllMemories: () => request<void>("/api/memories?confirm=true", { method: "DELETE" }),

    knowledgeStatus: () => request<KnowledgeOverview>("/api/knowledge/status"),
    listDocuments: (projectId?: string) =>
      request<KnowledgeDocument[]>(
        `/api/knowledge/documents${projectId ? `?project_id=${encodeURIComponent(projectId)}` : ""}`,
      ),
    getDocument: (id: string) => request<KnowledgeDocumentDetail>(`/api/knowledge/documents/${id}`),
    /** Upload a file to EZO's knowledge base (PDF, DOCX, XLSX, CSV, TXT, Markdown, images). */
    uploadDocument: (file: Blob, filename: string, projectId?: string | null) => {
      const form = new FormData();
      form.append("file", file, filename);
      if (projectId) form.append("project_id", projectId);
      return request<KnowledgeUploadResult>("/api/knowledge/documents", { method: "POST", body: form });
    },
    addUrl: (url: string, projectId?: string | null) =>
      request<KnowledgeUploadResult>("/api/knowledge/urls", {
        method: "POST",
        ...json({ url, project_id: projectId ?? null }),
      }),
    reindexDocument: (id: string) =>
      request<KnowledgeDocument>(`/api/knowledge/documents/${id}/reindex`, { method: "POST" }),
    deleteDocument: (id: string) => request<void>(`/api/knowledge/documents/${id}`, { method: "DELETE" }),
    searchKnowledge: (query: string, projectId?: string | null) =>
      request<KnowledgeSearchResult>("/api/knowledge/search", {
        method: "POST",
        ...json({ query, project_id: projectId ?? null }),
      }),

    voiceStatus: () => request<VoiceStatus>("/api/voice/status"),
    /** Send a short recording; the API transcribes it and keeps no audio. */
    transcribe: (audio: Blob, filename: string, language?: string | null, signal?: AbortSignal) => {
      const form = new FormData();
      form.append("audio", audio, filename);
      if (language) form.append("language", language);
      return request<VoiceTranscript>("/api/voice/transcribe", { method: "POST", body: form, signal });
    },
    /** Read text aloud with the server voice; resolves to MP3 audio. */
    speak: async (text: string, language?: string | null, signal?: AbortSignal): Promise<Blob> => {
      const response = await send("/api/voice/speak", { method: "POST", ...json({ text, language }), signal });
      return response.blob();
    },

    getAgentRun: (id: string) => request<AgentRun>(`/api/agent-runs/${id}`),

    /**
     * Send a chat message and receive the reply as a stream of events.
     * Pass an AbortSignal to stop generation.
     */
    async *streamChat(body: ChatRequestBody, signal?: AbortSignal): AsyncGenerator<ChatStreamEvent> {
      const response = await send("/api/chat/stream", {
        method: "POST",
        body: JSON.stringify(body),
        signal,
      });
      if (!response.body) throw new ApiError(0, "no_stream", "The browser cannot read streams.");
      const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
      const parser = new SseParser();
      try {
        while (true) {
          const { value, done } = await reader.read();
          const raw = done ? parser.flush() : parser.push(value);
          for (const event of raw) {
            if (STREAM_EVENTS.has(event.event)) {
              yield { type: event.event, data: JSON.parse(event.data) } as ChatStreamEvent;
            }
          }
          if (done) break;
        }
      } finally {
        reader.releaseLock();
      }
    },
  };
}

export type ApiClient = ReturnType<typeof createApiClient>;

async function toApiError(response: Response): Promise<ApiError> {
  try {
    const body = (await response.json()) as {
      error?: { code?: string; message?: string; hint?: string };
    };
    const error = body.error ?? {};
    return new ApiError(
      response.status,
      error.code ?? `http_${response.status}`,
      error.message ?? response.statusText,
      error.hint,
    );
  } catch {
    return new ApiError(response.status, `http_${response.status}`, response.statusText);
  }
}
