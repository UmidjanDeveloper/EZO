/**
 * Types for the EZO HTTP API.
 * Keep in sync with apps/api/src/ezo_api/schemas/api.py.
 */

export type LanguageCode = "uz" | "en" | "ru";
export type ResponseLanguage = "auto" | LanguageCode;
export type HumorPreference = "default" | "off" | "light" | "normal";

export interface Preferences {
  ui_language: LanguageCode;
  response_language: ResponseLanguage;
  humor: HumorPreference;
  auto_memory: boolean;
}

export interface User {
  id: string;
  email: string;
  display_name: string;
  preferences: Preferences;
}

export interface Project {
  id: string;
  name: string;
  description: string;
  status: "active" | "archived";
  created_at: string;
  updated_at: string;
}

export interface Conversation {
  id: string;
  title: string;
  project_id: string | null;
  created_at: string;
  updated_at: string;
}

export type ChatChannel = "text" | "voice";

export interface MessageMetadata {
  channel?: ChatChannel;
  provider?: string | null;
  model?: string | null;
  route?: string | null;
  requested_agent?: string;
  requested_agent_available?: boolean;
  finish_reason?: string | null;
  truncated?: boolean;
  memories_used?: string[];
  memories_saved?: number;
}

export interface Message {
  id: string;
  conversation_id: string;
  role: "user" | "assistant";
  content: string;
  language: string | null;
  agent: string | null;
  agent_run_id: string | null;
  metadata: MessageMetadata;
  created_at: string;
}

export type MemoryCategory = "preference" | "personal" | "goal" | "learning" | "decision" | "fact";

export interface Memory {
  id: string;
  memory_type: "profile" | "project";
  category: MemoryCategory | string;
  content: string;
  project_id: string | null;
  source: "auto" | "user" | string;
  source_conversation_id: string | null;
  confidence: number;
  importance: number;
  sensitive: boolean;
  last_accessed: string | null;
  created_at: string;
  updated_at: string;
}

export interface TraceStep {
  name: string;
  status: string;
  duration_ms: number;
  summary: string;
}

export interface ProviderAttempt {
  provider: string;
  model: string;
  status: "ok" | "failed";
  latency_ms: number;
  error_kind: string | null;
  error: string | null;
}

export interface AgentRun {
  id: string;
  conversation_id: string | null;
  status: "running" | "completed" | "failed";
  intent: string | null;
  intent_confidence: number | null;
  agent: string | null;
  language: string | null;
  route: string | null;
  provider: string | null;
  model: string | null;
  latency_ms: number | null;
  input_tokens: number | null;
  output_tokens: number | null;
  steps: TraceStep[];
  attempts: ProviderAttempt[];
  tool_calls: unknown[];
  error: string | null;
  created_at: string;
  finished_at: string | null;
}

export interface ProviderStatus {
  name: string;
  display_name: string;
  configured: boolean;
  capabilities: string[];
}

export interface AgentInfo {
  key: string;
  names: Record<LanguageCode, string>;
  description: string;
  available: boolean;
  milestone: number;
}

export interface RouteCandidate {
  provider: string;
  model: string;
  effort: string | null;
}

export interface SystemStatus {
  version: string;
  environment: string;
  database: string;
  offline_mode: boolean;
  providers: ProviderStatus[];
  routing: {
    offline: boolean;
    preferred_provider: string | null;
    routes: Record<string, { description: string; active_candidates: RouteCandidate[] }>;
  };
  agents: AgentInfo[];
  personality: {
    name: string;
    tagline: string;
    traits: string[];
    humor: string;
    modes: Record<string, string>;
  };
  debug_traces: boolean;
}

/* ---- streaming chat events (Server-Sent Events) ---- */

export interface ChatMetaEvent {
  conversation_id: string;
  conversation_title: string;
  created_conversation: boolean;
  user_message_id: string;
  run_id: string;
  intent: string;
  intent_confidence: number;
  agent: string;
  requested_agent: string;
  requested_agent_available: boolean;
  language: LanguageCode;
}

export interface ChatDeltaEvent {
  text: string;
}

export interface ChatDoneEvent {
  message: Message;
  run: {
    id: string;
    provider: string | null;
    model: string | null;
    latency_ms: number | null;
    input_tokens: number | null;
    output_tokens: number | null;
  };
}

export interface ChatErrorEvent {
  code: string;
  message: string;
  hint: string;
  run_id: string;
  attempts: ProviderAttempt[];
}

export type ChatStreamEvent =
  | { type: "meta"; data: ChatMetaEvent }
  | { type: "delta"; data: ChatDeltaEvent }
  | { type: "done"; data: ChatDoneEvent }
  | { type: "error"; data: ChatErrorEvent };

export interface ChatRequestBody {
  message: string;
  conversation_id?: string | null;
  project_id?: string | null;
  agent?: string | null;
  /** "voice" asks EZO for short, spoken-style replies. */
  channel?: ChatChannel;
}
