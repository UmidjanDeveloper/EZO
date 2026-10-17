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
  /** Sources the answer actually cites, verified by the API (never invented). */
  citations?: SourceCitation[];
  sources_considered?: number;
  /** Files EZO created (or the user saved) in this turn. */
  artifacts?: ArtifactRef[];
}

/** One numbered source behind an answer: a file passage or a web page. */
export interface SourceCitation {
  n: number;
  kind: "file" | "web_page" | "web";
  title: string;
  excerpt: string;
  source_name: string;
  url: string | null;
  date: string | null;
  document_id: string | null;
  revision_number: number | null;
  chunk_index: number | null;
  page_start: number | null;
  page_end: number | null;
  heading: string | null;
  location: string;
  reliability: number;
  primary: boolean;
}

export type KnowledgeStatus = "queued" | "processing" | "indexed" | "partial" | "needs_ocr" | "failed";

export interface KnowledgeDocument {
  id: string;
  title: string;
  filename: string | null;
  source_id: string;
  source_type: "upload" | "url" | "connector";
  source_name: string;
  project_id: string | null;
  mime_type: string;
  source_url: string | null;
  size_bytes: number;
  language: string | null;
  status: KnowledgeStatus;
  error: string | null;
  chunk_count: number;
  current_revision: number | null;
  created_at: string;
  updated_at: string;
  indexed_at: string | null;
  metadata: Record<string, unknown>;
}

export interface KnowledgeDocumentDetail extends KnowledgeDocument {
  revisions: { id: string; revision_number: number; content_hash: string; chars: number; created_at: string; current: boolean }[];
  chunks_preview: { chunk_index: number; text: string; metadata: Record<string, unknown> }[];
}

export interface KnowledgeUploadResult {
  document: KnowledgeDocument;
  duplicate: boolean;
  new_revision: boolean;
}

export interface KnowledgeOverview {
  vector_store: string;
  embedding_model: string | null;
  semantic_search: boolean;
  web_search: string | null;
  max_upload_mb: number;
  allowed_extensions: string[];
  documents: number;
  chunks: number;
  by_status: Record<string, number>;
}

export interface KnowledgeSearchResult {
  mode: "hybrid" | "keyword" | "vector" | "none";
  results: SourceCitation[];
  diagnostics: Record<string, unknown>;
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
  /** planned | experimental | alpha | beta | stable */
  maturity: Maturity;
  /** Roadmap section (ROADMAP.md). */
  phase: string;
}

export type Maturity = "planned" | "experimental" | "alpha" | "beta" | "stable";

export interface FeatureInfo {
  key: string;
  name: string;
  phase: string;
  maturity: Maturity;
  note: string;
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
  features: FeatureInfo[];
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

/** What EZO is visibly doing before it answers: "searching", "reading", "working", … */
export interface ChatActivityEvent {
  stage: string;
}

export type ChatStreamEvent =
  | { type: "meta"; data: ChatMetaEvent }
  | { type: "activity"; data: ChatActivityEvent }
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

export interface VoiceAttempt {
  provider: string;
  ok: boolean;
  kind: string | null;
  message: string | null;
}

/** Server-side speech providers. Empty lists mean the browser's speech features are used. */
export interface VoiceStatus {
  speech_to_text: string[];
  text_to_speech: string[];
  realtime: boolean;
  max_audio_mb: number;
  stores_audio: boolean;
  browser_fallback: boolean;
}

export interface VoiceTranscript {
  text: string;
  language: string | null;
  provider: string;
  attempts: VoiceAttempt[];
}

export type ArtifactType =
  | "document"
  | "spreadsheet"
  | "presentation"
  | "image"
  | "video"
  | "audio"
  | "code"
  | "report"
  | "research"
  | "other";

export interface ArtifactRef {
  id: string;
  title: string;
  type: ArtifactType | string;
  version: number;
}

/** One immutable version of an artifact. */
/** A file derived from a version: a presentation's PDF, web version and slide previews, … */
export interface ArtifactExport {
  name: string;
  filename: string;
  mime_type: string;
  size: number;
}

export interface ArtifactVersion {
  id: string;
  version_number: number;
  filename: string;
  mime_type: string;
  file_size: number;
  content_hash: string;
  provider: string | null;
  model: string | null;
  created_by: string;
  change_summary: string | null;
  parent_version_id: string | null;
  generation_metadata: Record<string, unknown>;
  source_references: SourceCitation[];
  created_at: string;
  current: boolean;
  is_text: boolean;
  exports: ArtifactExport[];
}

export interface Artifact {
  id: string;
  title: string;
  type: ArtifactType;
  status: "draft" | "generating" | "ready" | "failed";
  project_id: string | null;
  conversation_id: string | null;
  created_by_agent: string | null;
  provider: string | null;
  model: string | null;
  metadata: Record<string, unknown>;
  source_references: SourceCitation[];
  current_version: ArtifactVersion | null;
  version_count: number;
  created_at: string;
  updated_at: string;
}

export interface ArtifactDetail extends Artifact {
  versions: ArtifactVersion[];
}

export interface StoryScene {
  id: string;
  index: number;
  title: string;
  purpose: string;
  layout: string;
  text: string;
  visual_direction: string;
  speaker_notes: string;
  duration_seconds: number;
  transition: string;
  metadata: Record<string, unknown>;
  narration: { text: string; voice: string; timing: Record<string, unknown> } | null;
  assets: { id: string; scene_id: string | null; asset_type: string; artifact_id: string | null; source: string; metadata: Record<string, unknown> }[];
}

export interface StorySummary {
  id: string;
  title: string;
  goal: string;
  audience: string;
  language: string;
  format: "presentation" | "video" | "both";
  visual_style: string;
  aspect_ratio: string;
  project_id: string | null;
  scene_count: number;
  created_at: string;
  updated_at: string;
}

export interface Story extends StorySummary {
  metadata: Record<string, unknown>;
  scenes: StoryScene[];
  timeline: { scene_id: string; start_seconds: number; end_seconds: number; animation: Record<string, unknown> }[];
  total_seconds: number;
}
