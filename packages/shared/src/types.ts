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
  /** Uploaded documents attached to a user message (ids, and their names). */
  attachments?: string[];
  attachment_names?: string[];
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

export interface ImageProviderInfo {
  name: string;
  model: string;
  /** Can also edit existing images. */
  edit: boolean;
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
  /** Image providers in fallback order; empty when no image generation is configured. */
  image_providers: ImageProviderInfo[];
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
  /** Measured speaking time of a voice message, in seconds (Language Coach). */
  speech_seconds?: number | null;
  /** Uploaded documents this message is about, in the user's order (max 20). */
  attachments?: string[];
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

// --- Language Coach -----------------------------------------------------------------------

export type PronunciationConfidence = "not_assessed" | "transcript_assisted" | "limited" | "acoustic";

export interface LanguageSession {
  id: string;
  mode: string;
  language: string;
  status: "active" | "completed" | "abandoned";
  cefr_target: string | null;
  cefr_estimate: string | null;
  ielts_part: number | null;
  started_at: string;
  ended_at: string | null;
  speaking_seconds: number;
  user_words: number;
  /** Estimated IELTS-style range from the simulator — never an official score. */
  band_low: number | null;
  band_high: number | null;
  fluency_score: number | null;
  lexical_score: number | null;
  grammar_score: number | null;
  pronunciation_score: number | null;
  pronunciation_confidence: PronunciationConfidence;
  feedback: string | null;
  conversation_id: string | null;
  report_artifact_id: string | null;
}

export interface LanguageMistake {
  category: string;
  original: string;
  correction: string;
  explanation: string;
  severity: "minor" | "major";
}

export interface LanguageSessionDetail extends LanguageSession {
  strengths: string[];
  weaknesses: string[];
  practice_target: string;
  notes: string[];
  turns: { position: number; role: "learner" | "coach"; text: string; channel: string; ielts_part: number | null; word_count: number; speech_seconds: number | null }[];
  metrics: { name: string; value: number; scale: string; method: "computed" | "estimated"; confidence: string }[];
  mistakes: LanguageMistake[];
}

export interface LanguageGoal {
  id: string;
  description: string;
  target_band: number | null;
  cefr_target: string | null;
  deadline: string | null;
  status: string;
  created_at: string;
}

export interface LanguageProgress {
  sessions: LanguageSession[];
  speaking_minutes: number;
  criteria_trend: Record<string, { older: number; newer: number }>;
  recurring_mistakes: { category: string; count: number; sessions: number; example: string }[];
  goals: LanguageGoal[];
}

export interface VocabularyItem {
  term: string;
  meaning: string;
  example: string;
  times_suggested: number;
  status: string;
  created_at: string;
}

/** Who the user writes for: letterhead, contacts, house style (all entered by the user). */
export interface OrganizationProfileInput {
  name: string;
  org_type: "government" | "university" | "school" | "company" | "research" | "nonprofit" | "other";
  department?: string | null;
  address?: string | null;
  phone?: string | null;
  email?: string | null;
  website?: string | null;
  head_position?: string | null;
  head_name?: string | null;
  letterhead?: string | null;
  style_notes?: string | null;
  terminology?: Record<string, string>;
  is_default?: boolean;
  formatting?: OrganizationFormatting;
}

/** Standard document formatting of an organization (A4; centimetres and points). */
export interface OrganizationFormatting {
  font_name: string;
  font_size: number;
  line_spacing: number;
  indent_cm: number;
  margins_cm: { top: number; bottom: number; left: number; right: number };
}

export interface OrganizationProfile extends OrganizationProfileInput {
  id: string;
  has_logo: boolean;
  formatting: OrganizationFormatting;
}

/** An approved DOCX template or an example document of an organization. */
export interface OrganizationFile {
  id: string;
  kind: "template" | "example";
  title: string;
  filename: string;
  mime_type: string;
  size_bytes: number;
  doc_type: string | null;
  /** Templates: whether the {{matn}} marker shows where the text goes. */
  has_marker: boolean | null;
  excerpt: string | null;
}

/** A document type EZO can write (Professional Writing catalog). */
export interface WritingDocumentType {
  key: string;
  names: Record<string, string>;
  layout: string;
  mode: string;
  draft: boolean;
}

/** Translation (Stage C). */
export type TranslationLanguage = "uz" | "uz-cyrl" | "ru" | "en";
export type GlossaryLanguage = "uz" | "ru" | "en";
export type TranslationDomain = "general" | "official" | "academic" | "business" | "technical" | "legal";

export interface TranslateRequest {
  text: string;
  target: TranslationLanguage;
  source?: TranslationLanguage | null;
  domain?: TranslationDomain;
  use_glossary?: boolean;
  organization_id?: string | null;
}

/** EZO's checks of a translation against its source (warnings, nothing is changed). */
export interface TranslationQuality {
  ok: boolean;
  paragraphs: number;
  missing_numbers: string[];
  extra_numbers: string[];
  links_changed: string[];
  names_to_check: string[];
  terms_missing: string[];
  terms_used: number;
  empty_paragraphs: number[];
  untranslated_paragraphs: number[];
  length_warnings: number[];
  script_note: string | null;
  ambiguities: string[];
}

export interface TranslateResult {
  text: string;
  source_language: TranslationLanguage;
  target_language: TranslationLanguage;
  /** "model" or "transliteration" (Uzbek script change, no AI model). */
  method: string;
  quality: TranslationQuality;
  warnings: string[];
  terms: { source: string; target: string }[];
  provider: string | null;
  model: string | null;
}

export interface TransliterateResult {
  text: string;
  from_script: "latin" | "cyrillic" | null;
  to: "latin" | "cyrillic";
  engine: string;
}

export interface GlossaryTermInput {
  source_language: GlossaryLanguage;
  target_language: GlossaryLanguage;
  source_term: string;
  target_term: string;
  note?: string | null;
  organization_id?: string | null;
}

export interface GlossaryTerm extends GlossaryTermInput {
  id: string;
}

/** Career profile (Stage D): the only facts a CV and application letters are built from. */
export interface CareerExperience {
  role: string;
  organization?: string;
  location?: string;
  start?: string;
  end?: string;
  achievements?: string[];
}

export interface CareerEducation {
  institution: string;
  degree?: string;
  field?: string;
  start?: string;
  end?: string;
  notes?: string;
}

export interface CareerProfile {
  full_name: string;
  headline?: string | null;
  email?: string | null;
  phone?: string | null;
  location?: string | null;
  links?: string[];
  summary?: string | null;
  experience?: CareerExperience[];
  education?: CareerEducation[];
  skills?: string[];
  languages?: { language: string; level?: string }[];
  certificates?: { name: string; issuer?: string; year?: string }[];
}
