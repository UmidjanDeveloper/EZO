# EZO architecture

This document explains how EZO is built, why, and where to extend it. It describes the code
as it exists today (Foundation through Presentations, plus the orchestration foundation); the
order of future work is in [ROADMAP.md](ROADMAP.md).

## Overview

```
┌──────────────────────┐   HTTP + SSE    ┌──────────────────────────────────────────────┐
│ apps/web (Next.js)   │ ──────────────▶ │ apps/api (FastAPI)                           │
│ chat · projects ·    │                 │                                              │
│ memory · settings    │ ◀────────────── │  routes → EzoCore → Agent → ModelRouter      │
│ packages/ui, shared  │  streamed reply │              │          │        │           │
└──────────────────────┘                 │        MemoryService  Personality  Providers  │
                                         │              │                    │           │
                                         └──────────────┼────────────────────┼───────────┘
                                                        ▼                    ▼
                                                  PostgreSQL          Anthropic / OpenAI /
                                                  (SQLite in tests)   Gemini (or offline)
```

- **Frontend:** Next.js (App Router), React, TypeScript, Tailwind CSS v4, Framer Motion.
- **Backend:** Python, FastAPI, Pydantic, SQLAlchemy 2 (async), Alembic migrations.
- **Database:** PostgreSQL with pgvector. The schema is portable,
  so tests and the no-Docker quick mode run on SQLite.
- **Monorepo:** pnpm workspace for TypeScript (`apps/web`, `packages/*`, `tests/e2e`);
  `uv` project for Python (`apps/api`).

### Mapping to the planned structure

The specification proposes `packages/agents`, `packages/tools`, `packages/memory`,
`packages/rag`, `packages/providers`. Those are Python concerns, so they live as clearly
separated sub-packages of the API instead of separate installable packages (one Python
project is much easier to install, test and debug):

| Planned | Where it lives now |
|---|---|
| `packages/agents` | `apps/api/src/ezo_api/agents/` |
| `packages/providers` | `apps/api/src/ezo_api/providers/` |
| `packages/memory` | `apps/api/src/ezo_api/memory/` |
| `packages/tools`, `packages/rag` | `ezo_api/tools/`, `ezo_api/knowledge/` |
| `packages/ui` | `packages/ui/` (React components) |
| `packages/shared` | `packages/shared/` (API types + client) |
| `services/worker` | Not yet (ROADMAP *Infrastructure*: durable jobs, Redis) |
| `knowledge/`, `infra/` | `ezo_api/knowledge/`; `infra/` not yet |
| `tests/` | `tests/e2e/` (browser); unit/integration tests sit next to the API in `apps/api/tests/` |

If the Python side grows large enough, any sub-package can be extracted into its own `uv`
workspace member without changing its imports.

## Backend (`apps/api/src/ezo_api`)

```
main.py            app factory: middleware, error handlers, routers
settings.py        all configuration from environment variables / .env
services.py        builds the service container (DB, auth, router, core…)
api/routes/        HTTP endpoints: chat, conversations, memory, projects, knowledge, system
core/              EzoCore pipeline, language detection, intent classification, tracing
agents/            Agent interface, catalog (availability per milestone), GeneralAgent, ResearchAgent
tools/             Tool interface, ToolRegistry (validation, permissions, timeouts, audit),
                   knowledge_search, web_search (Tavily / Claude), web_fetch, source reliability
knowledge/         uploads (validation), parsers, ingestion pipeline + runner, embeddings,
                   vector stores (pgvector / local), retrieval (keyword + vector + RRF),
                   citations, SSRF-safe fetcher
storage/           StorageProvider interface + LocalStorageProvider (S3 later)
voice/             SpeechToTextProvider / TextToSpeechProvider / RealtimeVoiceProvider
                   interfaces, OpenAI-compatible adapter (OpenAI, VoiceStudio), fallback service
providers/         ModelProvider interface, adapters, router with fallback, offline mode
memory/            extraction + importance scoring, sensitivity filter, retrieval
personality/       personality profile (TOML) and system-prompt composition
auth/              AuthBackend abstraction, single-owner implementation
security/          rate limiter, audit log
db/                SQLAlchemy models, async session, portable column types
schemas/           Pydantic request/response models (mirrored in packages/shared)
```

### EzoCore: one turn

`core/ezo_core.py` turns a user message into a reply in two phases. `prepare` runs before the
HTTP response starts, so bad input becomes a normal 4xx error; `execute` streams.

| Step | What happens | Where |
|---|---|---|
| detect_language | uz / en / ru (Uzbek Latin & Cyrillic aware), or the user’s fixed preference | `core/language.py` |
| classify_intent | transparent multilingual rules with weights; records matched signals | `core/intent.py` |
| select_agent | intent → agent; unavailable agents are covered by GeneralAgent | `agents/registry.py` |
| *(persist)* | user message + an `AgentRun` (status `running`) are committed | |
| load_context | recent messages within a character budget | |
| retrieve_memory | profile (+ current project) memories ranked by relevance, importance, recency | `memory/service.py` |
| plan | agent chooses route (chat/reasoning/coding…), context mode and instructions | `agents/general.py` |
| gather | the agent uses tools before answering (file search, web search, page reading); each tool start is streamed as an `activity` stage | `agents/*.py`, `tools/` |
| compose_prompt | personality + rules + mode + language + memories + numbered sources + notes + date | `personality/prompt.py` |
| route_model / generate | stream from the first working candidate; fall back before the first token | `providers/router.py` |
| verify | empty reply, refusal and truncation handling | |
| verify_citations | keep only `[n]` markers that match a retrieved source; store cited sources on the message | `knowledge/retrieval/citations.py` |
| save_memory | capture meaningful, non-sensitive statements from the user message | `memory/extraction.py` |
| *(persist)* | assistant message, run status, provider, model, tokens, latency, steps | |

Streaming uses Server-Sent Events with five event types: `meta` (conversation, routing),
`activity` (what EZO is visibly doing: `searching`, `reading`, `coding`, `creating`,
`working`), `delta` (text), `done` (saved message + run summary, with `metadata.citations`)
and `error` (code, message, hint).
`POST /api/chat` offers the same pipeline without streaming.

### Agents

`agents/catalog.py` lists every agent with its roadmap **phase**, **maturity** (`planned`,
`experimental`, `alpha`, `beta`, `stable`; availability is derived from it, so a planned agent
can never be selected), preferred route, context mode and a **limitation note**.
`maturity.py` does the same for non-agent capabilities; both are returned by `/api/status`
and checked against ROADMAP.md by a test. Implemented: `GeneralAgent` (searches the user's files when
they exist, strict relevance gate), `ResearchAgent` (plans queries with a fast model,
searches files and the web, ranks by primary source / reliability / recency, reads the top
pages, answers with dated citations; honest note when web search is not configured),
`DocumentAgent` and `PresentationAgent` (see *Documents and presentations* below). When the
intent asks for an unavailable agent (e.g. images), `GeneralAgent` handles the turn and
its prompt contains that agent’s limitation note, so it does not pretend to export files,
browse the web or cite laws it cannot verify. Agent selection is invisible in the UI (visible
only in the debug trace).

Adding an agent: subclass `Agent` (`agents/base.py`), implement `plan()` (and optionally
`gather()` to use tools), mark it
`available=True` in the catalog and register it in `AgentRegistry`.

### Model providers and routing

- `providers/base.py` — `ModelProvider` interface: `stream_chat()` (required), `chat()`, and
  capability methods (`embed()` …) that raise `CapabilityNotAvailableError` until implemented.
- Adapters use the official SDKs: `anthropic_provider.py`, `openai_provider.py`,
  `gemini_provider.py`. All map vendor errors to `ProviderError` kinds
  (`auth`, `rate_limit`, `model_not_found`, `unavailable`, `timeout`, …).
- `providers/router.py` — `ModelRouter` reads `config/models.toml`. Each *route* (chat,
  reasoning, coding, long_context, vision) has ordered candidates. Only providers with a key
  are used; `EZO_PREFERRED_PROVIDER` moves one provider first. `RoutedStream` tries the next
  candidate when a provider fails **before** producing text; a failure mid-answer is reported,
  not silently retried (the user would see two different answers glued together).
- `providers/offline.py` — used only when no key is configured. It is not an AI model; it
  explains, in the user's language, how to connect one.

For Claude Opus/Sonnet-class models the Anthropic adapter enables the API’s server-side
refusal fallback. No `temperature` is sent (several current models reject it).

Adding a provider: implement `ModelProvider.stream_chat`, register it in
`providers/registry.py`, add its key to `settings.py` / `.env.example`, and list it in
`models.toml`.

### Memory

Three layers:

1. **Conversation memory** — the message history itself (`messages` table).
2. **Profile memory** — stable facts and preferences (`memory_type = profile`).
3. **Project memory** — decisions and facts of one project (`memory_type = project`).

Capture (`memory/extraction.py`): a sentence becomes a candidate only if it matches a
meaningful pattern — explicit (“eslab qol…”, “remember that…”, “запомни…”), preference,
personal fact, goal, learning difficulty, decision — each with an importance and confidence
score. Questions are ignored. `memory/sensitive.py` blocks passwords, API keys, card numbers
(Luhn-checked), passport numbers and bank accounts from automatic storage. Repeating a
statement reinforces the existing memory instead of duplicating it.

Retrieval (`memory/service.py`, `memory/scoring.py`): when an embedding model is available,
memories are embedded on create/update and ranked by a hybrid score —
`0.45 × semantic + 0.15 × lexical + 0.2 × importance + 0.1 × recency + 0.1 × project` — with a
minimum semantic similarity so unrelated memories are not injected. Without embeddings, the
original lexical score is used (`0.6 × relevance + 0.25 × importance + 0.15 × recency`,
prefix stemming for Uzbek/Russian suffixes). Very important profile memories are always included.

### Knowledge, retrieval and citations

```
upload / URL ─► validate (extension + content sniffing, size, zip-bomb limits, safe name, SHA-256)
            ─► StorageProvider (content-addressed keys; no path traversal)
            ─► IngestionRunner (background task, persisted status, resumes after restart)
                 parse ─► normalise ─► metadata ─► chunk (~1200 chars, overlap 150, pages/headings kept)
                 ─► DocumentRevision (new content = new revision; old ones kept, never overwritten)
                 ─► embed (one active model, "provider:model" stored with every vector)
                 ─► index (VectorStore: pgvector on PostgreSQL, numpy store otherwise)
question ─► Retriever: keyword (PostgreSQL full-text / BM25 on SQLite) + vector search
            ─► Reciprocal Rank Fusion ─► relevance gate (strict for casual chat) ─► max 3 per document
            ─► numbered SourceRefs (title, file/URL, page, revision, date, reliability)
answer   ─► verify_citations removes numbers that match no source; cited sources stored on the message
```

Statuses: `queued → processing → indexed | partial (no embeddings: keyword only) | needs_ocr
(images/scans, OCR in ROADMAP Phase 3) | failed (with a readable reason)`. Only the current
revision of `indexed`/`partial` documents is searchable. Source text is wrapped in `<source>`
tags and the prompt tells the model to treat it as data, not instructions.

Web: `tools/web_search.py` uses Tavily (`TAVILY_API_KEY`) or Claude's server-side web search
tool; `knowledge/fetch.py` (`SafeFetcher`) resolves DNS and refuses private, loopback,
link-local and CGNAT addresses on every redirect hop, checks `robots.txt`, limits size,
content type and time. `tools/reliability.py` scores domains (official `gov.uz`/`.gov` 0.95,
academic 0.85, established news 0.7 … social 0.35).

Every tool call goes through `ToolRegistry.execute`: Pydantic argument validation, unknown and
dangerous tools denied (dangerous ones need explicit confirmation), timeout, and
a `tool_calls` row with redacted arguments.

Users see, add and delete memories on the **Memory** page (and per project). Automatic memory
can be switched off in Settings.

### Artifacts and story projects

`artifacts/service.py` (`ArtifactService`) is the only code that writes artifact content:

- `create()` adds the artifact and version 1.
- `add_version()` adds a new version, or nothing if the content is identical.
- `restore()` copies an old version forward as a new version, with `parent_version_id`
  pointing to the original.
- `delete()` removes everything after an explicit confirmation, and only deletes stored files
  no other version still uses.

Content is stored through the existing `StorageProvider` under
`artifacts/<user>/<hash[:2]>/<hash>.<ext>`. The MIME type comes from an extension allow-list,
never from the caller. Downloads are sent as `attachment` with `X-Content-Type-Options:
nosniff` and `Content-Security-Policy: sandbox`, so HTML or SVG artifacts never run in the
API's origin.

Agents report what they created in `Gathered.artifacts`. EzoCore stores it in the message's
`metadata.artifacts`, and the web app shows a card under the answer.

`story/service.py` (`StoryService`) manages story projects. `story/timeline.py` plans a
sequential timeline in which a scene lasts its planned duration, or longer if its narration
needs more time (about 2.4 words per second), so narration is never cut off.

### Documents and presentations

Format services live in `documents/` and know nothing about agents or models:

- `model.py` + `markdown_io.py`: a format-neutral `DocumentSpec` parsed from Markdown.
- `docx/`, `pdf/`, `spreadsheet/` writers; `spreadsheet/analysis.py` computes column facts
  (types, missing values, sum/mean/median/min/max, top values) without pandas.
- `compare.py`: paragraph-level diff.
- `pdf/engine.py` + `pdf/plan.py` + `pdf/requests.py`: the offline PDF engine (pypdf for
  structure, pypdfium2 for rendering, reportlab for stamps), multi-step plans with page
  identity, and the uz/ru/en request parser. Every output is reopened and verified.
- `ocr/`: `OCRProvider`; `TesseractOCRProvider` (fixed argv, no shell, stdin, timeout,
  output limit; packs checked against `--list-langs`), `preprocess.py` (contrast, upscale,
  deskew), `export.py` (editable / layout DOCX, searchable PDF). Per-page results live in
  `ocr_pages` (migration 0006).
- `docx/fidelity.py`: in-place Word editing on the original XML (run segments, ⟦k⟧ markers,
  difflib fallback, tracked changes, structural inventory before/after).
- `tables.py`: Word tables, PDF word boxes (PDFium) and OCR word boxes → detected tables.
  `spreadsheet/ops.py`: deterministic sheet operations and the formula report.
- `longdoc.py`: section-aware parts for long texts; per-part model results are cached in
  `long_doc_parts` (migration 0007) so long jobs resume.
- `render/`: the slide engine. `spec.py` validates a `DeckSpec` (24 layouts), `layouts.py`
  lays every slide out **once** into primitives on a 960×540 pt canvas, fitting text with the
  bundled Liberation Sans metrics (Arial-compatible), and four renderers draw the same plan:
  `pptx_renderer.py` (native text, bullets, charts, tables, notes), `pdf.py`, `png.py`
  (previews) and `html.py` (self-contained web version). `qa.py` checks the plan; `build.py`
  moves surplus bullets to the notes, renders, and re-opens the PPTX before it is reported.

Why python-pptx and not PptxGenJS: the API is Python, the layout is computed in Python once
for all four outputs, and python-pptx writes native, editable charts and tables without a
Node worker.

Agents use them only through logged tools (`tools/document_tools.py`): `read_document`,
`create_document`, `create_spreadsheet`, `create_presentation`. Helpers: `agents/llm.py`
(`complete()` through the router, `extract_json()`, `sources_block()` which wraps source
text as data) and `agents/references.py` (which uploaded file or EZO document a request
means, scoped to the project).

- **PresentationAgent**: sources (the referenced file, else knowledge search; web search when
  the topic needs current data) → one `reasoning`-route call returns a `DeckSpec` →
  `check_deck` QA → one repair call if there are errors → `create_presentation` (PPTX + PDF +
  web + previews + JSON spec as exports, a linked `StoryProject`) → a short report on the cheap
  `chat` route. “3-slaydni qisqartir” edits the conversation's latest deck into a new version.
- **DocumentAgent** first tries the deterministic EZO Office actions (`agents/office.py`:
  PDF operations and OCR; `agents/convert_office.py`: scan → Word/searchable PDF, tables,
  sheet operations; `agents/docx_office.py`: in-place Word edits and find-and-replace).
  They act on the files attached to the message, or on files the request clearly refers to.
  Long files go through `agents/longdoc_office.py`. Otherwise it picks an action without a
  model call (convert, compare, analyze, spreadsheet, transform, create, answer). Conversion and comparison need no model and work
  offline. Transformations of an upload create a derived artifact; of an EZO document, a new
  version. Both record `derived_from`, a change summary and diff statistics.

Version exports are stored under `artifacts/<user>/exports/<artifact>/` and listed in the
version's `generation_metadata.exports` (keys are internal; the API returns `exports` with
name, filename, type and size). `GET /api/artifacts/{id}/versions/{n}/exports/{name}`
serves them (PNG previews inline, everything else as attachments).

### Professional writing

`writing/` holds the document-type catalog (`catalog.py`: 30 types with fields,
sections, layout, default mode and draft flag), writing modes, Uzbek style rules and the
deterministic style check (`style.py`). It also has the drafting contract and validation
(`service.py`: JSON content from the model; invented numbers and dates removed or flagged;
approval claims flagged) and the official-layout DOCX renderer (`render.py`).
`agents/writing_office.py` runs the flow inside DocumentAgent: one model call, or none for
templates. EzoCore routes "<document type> + writing verb" to DocumentAgent.
Organization profiles live in `organization_profiles` (migration 0008) and are managed at
`/api/writing/organizations`.

### Translation

`translation/` holds the model-free parts: `translit.py` (Uzbek Latin ↔ Cyrillic rules,
span output for run-level Word edits), `languages.py` (codes uz, uz-cyrl, ru, en; reading
source/target and style from a request), `glossary.py` (matching terms with word endings
and either script, loading the user's and the default organization's terms), `quality.py`
(numbers, months, links, surnames, glossary use, paragraphs, script) and `documents.py`
(Word script conversion in place, bilingual Word files, paragraph pairs). `service.py` is
the text translation (paragraph batches, ambiguity notes; Cyrillic produced by converting
the model's Uzbek) and `interpreter.py` the turn-based voice interpreter plus the
`StreamingInterpreter` interface. In chat, `agents/translate_office.py` handles text in the
message, script conversion and glossary commands; files go through
`DocumentAgent._transform`, which adds the plan, glossary and a review hook to the
DOCX-fidelity editor (`transform_docx(review=…)`). EzoCore routes explicit translation
requests (`translation/requests.py`) to DocumentAgent unless a language practice session
is active. Terms live in `glossary_terms` (migration 0009); API under `/api/translation`.

### Education, academic research and career (Phase 4)

`education/` recognises requests and options (`catalog.py`: lesson, syllabus, rubric,
study plan, quiz, defense, interview), defines the JSON the model writes and EZO's checks
(`models.py`: answer key, timing, weights, points, counts) and renders Word Markdown,
Excel sheets and a DeckSpec (`render.py`). `agents/education_office.py` makes one model
call (or a template) and saves through the existing `create_document`,
`create_spreadsheet` and `create_presentation` tools. `academic/` has the citation styles
(`citations.py`), the OpenAlex client (`scholar.py`, through `SafeFetcher.fetch_json`),
the research-plan contract and checks (`plan.py`) and request recognition;
`agents/academic_office.py` runs search → plan → checks → reference list, and reference
formatting with field verification. `career/profile.py` is the career profile schema
(`career_profiles`, migration 0010), the facts block for prompts and the deterministic CV;
`agents/writing_office.py` uses it for CVs and letters. All of it runs inside
DocumentAgent; EzoCore routes these requests there. APIs: `/api/academic`, `/api/career`.

### Language Coach (Phase 1)

`agents/language_coach.py` keeps real session state (`db/models/language.py`, migration 0004).
`language/` holds the parts that need no model:
- `analysis.py`: exact metrics from the transcript;
- `modes.py`: mode, CEFR, command and goal detection;
- `ielts.py`: the original question bank, the Part 1 → 2 → 3 state machine and band maths;
- `assessment.py`: the assessor prompt and validation of its JSON (invented mistakes dropped,
  bands rounded and clamped, too-short samples get no band, pronunciation transcript-assisted
  and excluded from the range);
- `service.py`: sessions, turns, saving results, recurring mistakes and progress;
- `report.py`: the localized report artifact.

EzoCore keeps a conversation with an **active language session** on the coach. A general-intent
message, which is how most learner answers classify, is routed to the coach instead. Voice
messages may carry `speech_seconds` (measured by the web VAD), stored per turn for
words-per-minute. Practice replies use the `chat` route and the assessment uses `reasoning`.
Details: [docs/LANGUAGE_COACH.md](docs/LANGUAGE_COACH.md).

### Visual Agent (Phase 2)

`visual/` keeps EZO independent of image vendors:
- `base.py`: `ImageProvider` / `ImageEditProvider`, `ImageRequest`, `ImageError` kinds;
- `openai_images.py`, `gemini_images.py`: adapters (model IDs from settings);
- `service.py`: `VisualService`, the ordered fallback and limits; a `refused` error stops it;
- `images.py`: the safety gate (decode, format allowlist, pixel cap, re-encode to PNG,
  cover-fit crops for slides);
- `compose.py`: graphics EZO lays out itself (diagrams through the slide engine, social
  graphics, logo sheets); the picture is optional, the text is always EZO's;
- `kinds.py`: kind, aspect ratio, variants, social format, edit and "no images" rules.

`agents/visual.py` makes one `chat`-route call for the prompt or spec JSON. It then calls the
tools in `tools/visual_tools.py`: `generate_image`, `edit_image` and `create_graphic`. They
store versioned `image` artifacts with a preview, a `spec` export and full generation
metadata. EzoCore sends a general-intent edit ("fonini ko'k qil") to the Visual Agent when the
conversation's newest artifact is an image.

The slide engine has an `ImageBox` primitive in all four renderers. `PresentationAgent`
requests images for `hero_image` slides through `generate_image`, puts the artifact IDs in
the deck spec (ids from the model are discarded), and reuses them when a deck is edited.
`create_presentation` loads only the user's own image artifacts. Details:
[docs/VISUAL_AGENT.md](docs/VISUAL_AGENT.md).

### Official sources and legal research (Phase 7 foundation, experimental)

`official/` adds official legal texts to the existing knowledge base:
- `base.py`: `OfficialSourceConnector` (validate ID → official URL → parse) and each source's
  `AccessReview`; unverified sources cannot be enabled;
- `http.py`: `OfficialHttpClient` on top of `SafeFetcher` (host allow-list, robots.txt
  fail-closed, pacing, budget, no work-around for 401/403/451, Retry-After);
- `lexuz.py`: the LEX.UZ proof of concept; `registry.py`: all sources, planned ones included;
- `legal_text.py`: numbers, types, dates and status labels in Uzbek Latin/Cyrillic and Russian,
  plus Latin ↔ Cyrillic query variants;
- `sync.py`: `OfficialSyncService`, resumable runs with per-document checkpoints, hash-based
  new / unchanged / amended / duplicate, live verification.

The text goes through the normal `KnowledgeService` pipeline (Markdown → revision → chunks →
vectors), so retrieval and citation checks are unchanged. Legal metadata is in
`legal_documents` / `legal_revisions`, and runs are in `official_sync_runs` (migration 0005).
`agents/legal_research.py` uses the `official_search` and `verify_official_document` tools.
`/api/official` exposes sources, runs, documents and live checks. Details:
[docs/OFFICIAL_SOURCES.md](docs/OFFICIAL_SOURCES.md).

### Orchestration (prepared, not wired into chat)

`orchestration/` holds optional multi-agent **missions** behind one interface,
`OrchestrationProvider` (`plan_mission`, `start_mission`, `get_status`, `pause`, `resume`,
`cancel`, `submit_approval`, `list_agent_runs`, `get_result`). EzoCore stays the decision
maker: `complexity.assess()` decides deterministically whether a request is one agent's job
or a mission, and `draft_plan()` builds a small, validated dependency graph. The
`NativeOrchestrationProvider` runs it: parallel steps with scoped inputs, retries, timeouts,
approval gates, pause/resume/cancel and artifact linking. Every step returns a validated
`AgentOutput`, and a mission is never "completed" after a failed step.
`security.py` defines the boundary for a future, optional `RufloProvider` (MCP allow-list and
deny-list, secret redaction, hardened minimal environment). See
[docs/RUFLO_INTEGRATION_PLAN.md](docs/RUFLO_INTEGRATION_PLAN.md).

### Voice providers

`voice/base.py` defines `SpeechToTextProvider`, `TextToSpeechProvider` and
`RealtimeVoiceProvider` (interface only, ROADMAP Phase 8). `voice/openai_audio.py` implements
the first two over the OpenAI audio protocol and serves two providers: **OpenAI** and the
optional **VoiceStudio** service. VoiceStudio is a separate AGPL-3.0 process reached over
HTTP; its code is never imported. `VoiceService` tries the providers in
`EZO_VOICE_PROVIDERS` order (`auto` = VoiceStudio, then OpenAI) and records every attempt.
A `bad_audio` error stops the chain, because the recording itself is the problem.

`/api/voice/status` lists the providers. `/api/voice/transcribe` takes one recording
(size-limited and sniffed: WebM, Ogg, WAV, MP3, MP4) and returns the text.
`/api/voice/speak` returns MP3 with `Cache-Control: no-store`. Audio stays in memory only.
The transcript is sent as a normal chat message with `channel: "voice"`.

```
microphone ─► MediaRecorder + VAD (pause detection) ─► POST /api/voice/transcribe ─► provider chain
          └─(no server provider / server failed)─► browser SpeechRecognition
reply text ─► POST /api/voice/speak ─► <audio> (tap = interrupt) ─(fails)─► browser speechSynthesis
```

### Personality

`config/personality.toml` holds identity, traits, rules (no sycophancy, disagree politely,
separate facts from opinions, never invent sources/laws, say when information may be
outdated), humor levels and context modes (casual, professional, technical, teacher). It
changes *how* EZO speaks, never *what* is true. The prompt is assembled stable-parts-first so
provider prompt caching stays effective.

### Data model

All primary keys are UUIDs. Migrations live in `apps/api/migrations` (Alembic).

| Table | Purpose |
|---|---|
| `users` | owner account and preferences (UI language, reply language, humor, auto-memory) |
| `projects` | user projects |
| `conversations` | chat threads (optionally in a project) |
| `messages` | user and assistant messages with metadata (provider, model, route…) |
| `memories` | profile/project memories with importance, confidence, source, sensitivity, last access (vectors live in the vector store) |
| `agent_runs` | one trace per turn: intent, agent, route, provider, model, latency, tokens, steps, provider attempts, errors |
| `audit_logs` | deletions, memory changes, project creation, preference changes, uploads |
| `knowledge_sources` | where documents come from: uploads, a URL, later connectors (lex.uz…) |
| `knowledge_documents` | one file or page: title, type, size, content hash, status, error, current revision |
| `document_revisions` | every version of a document (content hash, storage key, extracted text) |
| `knowledge_chunks` | searchable passages of a revision with page/heading metadata (PostgreSQL GIN full-text index) |
| `vector_entries` | portable vector store (JSON vectors) used when pgvector is unavailable |
| `pgvector_entries` | PostgreSQL only, created by migration 0002 when the `vector` extension can be enabled |
| `tool_calls` | every tool execution: tool, redacted arguments, status, summary, error, duration |
| `artifacts` | things EZO created or the user saved: title, type, status, agent, provider, model, project, conversation, source references, current version |
| `artifact_versions` | immutable versions: number, storage key, filename, MIME type, size, content hash, provider, model, created by, change summary, parent version, generation metadata, sources |
| `story_projects` | one narrative (goal, audience, language, format, style, aspect ratio) behind slides or video |
| `story_scenes` | ordered scenes: title, purpose, layout, text, visual direction, speaker notes, duration, transition |
| `story_assets`, `story_narrations`, `story_timeline` | scene media (optionally artifacts), narration text/voice/timing, start/end/animation per scene |

`Artifact`, `Task`, `LanguageSession` and `LanguageMetric` arrive with the milestones that use
them, each with its own migration.

### Security

- Secrets only from environment variables; `.env` is git-ignored.
- `AuthBackend` abstraction; `LocalOwnerAuth` supports `local` (single owner, no login) and
  `token` (Bearer token, constant-time comparison) modes.
- Sliding-window rate limiting per client (chat and general buckets).
- Input validation with Pydantic; message length limit; ownership checks on every resource.
- SQLAlchemy ORM only (parameterized queries).
- Security headers on every response (pure ASGI middleware, safe for streaming).
- Audit log for important operations.
- Markdown from models is rendered without raw HTML; links open with `noopener`.
- Uploads: extension allow-list plus content sniffing, size limit, zip-bomb limits for
  Office files, sanitised display names, storage keys validated against traversal.
- Web fetching: SSRF protection on every redirect, robots.txt, size/type/time limits.
- Tools: validated arguments, timeouts, dangerous-tool denial, audit rows with redacted secrets.
- No shell or filesystem tools exist yet; when they arrive (ROADMAP Phase 9) they will require
  explicit permission and run sandboxed.

### Observability

Every turn writes an `AgentRun` with step names, durations and short summaries, provider
attempts (with error kinds), the selected provider/model, token usage and latency. The web
app’s **Iz (debug)** panel shows it. Hidden model reasoning is never stored.
`EZO_DEBUG_TRACES=false` disables the trace endpoints.

## Frontend (`apps/web`)

```
app/                  routes: / (chat), /chat/[id], /projects, /projects/[id], /memory,
                      /settings, /ezo-config (runtime config)
components/robot/     EzoRobot — animated SVG robot face; EzoPresence — orb around it with 11
                      visible states; EzoStatus — header status pill
components/artifacts/ Created page (versions, preview, edit, restore, download) and ArtifactCard
components/knowledge/ Files page (upload, link, status, versions, previews, delete/re-read)
components/chat/      ChatView (type/talk switch), useChatSession (conversation + streaming),
                      VoiceStage (hands-free voice loop), Composer, MessageBubble, TracePanel
components/layout/    AppShell + HistoryPanel (conversation history is the only navigation)
components/pages/     Projects, Memory, Settings
lib/voice/            voice engines (server recording + VAD, server speech, browser fallback)
lib/                  API client, speech (Web Speech API), i18n (uz/en/ru), theme, app state,
                      ezo-state (pure visible-state machine), knowledge helpers
```

- **Design principle:** the user only sees EZO (the robot) and the conversation history.
  Agents are chosen by EzoCore behind the scenes; nothing in the UI asks the user to pick one.
- **Voice loop** (`VoiceStage`): listen (browser speech recognition, uz-UZ / en-US / ru-RU) →
  send with `channel: "voice"` → stream the reply → read it aloud (speech synthesis, Markdown
  stripped) → listen again. Tapping the robot interrupts. With `channel: "voice"` EzoCore adds
  a prompt section asking for short, spoken-style answers; the channel is stored on the
  message. Typed and spoken turns share one conversation.
- **Visible state** (`lib/ezo-state.ts`): a pure reducer turns chat events (send, activity,
  delta, done, error) into one of `idle, listening, thinking, speaking, searching, reading,
  coding, creating, working, completed, error`. Unknown server stages show as `working`;
  `completed`/`error` settle back to `idle`. `EzoPresence` renders each state with its own
  subtle motion (original SVG/framer-motion; respects reduced motion).
- **Files in chat:** the paperclip uploads to the knowledge base (scoped to the current
  project) and shows a status chip; answers list their cited sources under the text.
- The API client (`packages/shared`) parses the SSE stream incrementally, supports
  cancelling generation and multipart uploads.
- `/ezo-config` serves the API URL from the `EZO_API_URL` environment variable at runtime, so
  the same build works in Docker, tests and development.
- Design tokens are CSS variables (`app/globals.css`) for light and dark themes; the palette
  takes Samarkand turquoise and lapis as accents.
- All interface text is in `lib/i18n/messages.ts`; TypeScript and a unit test ensure every
  language has every key.

## Testing

| Level | Tool | Location |
|---|---|---|
| Unit (Python) | pytest | `apps/api/tests/unit` — language, intent, memory, router, adapters (fake SDK clients), personality, rate limit |
| Integration (Python) | pytest + httpx ASGI | `apps/api/tests/integration` — full API with fake providers, real migrations, SQLite or PostgreSQL |
| Unit (TypeScript) | Vitest | `packages/shared` (SSE parser, client, uploads), `apps/web` (i18n, visible-state machine, EzoPresence/Sources rendering) |
| End-to-end | Playwright | `tests/e2e` — real browser, real API (offline mode, fresh SQLite) |

## Key decisions

- **Explicit pipeline instead of an agent framework.** EzoCore is a small, readable state
  machine with traced steps. LangGraph can be introduced for multi-agent workflows
  (ROADMAP *Missions*) if the explicit approach stops being enough.
- **Rule-based intent and language detection.** Deterministic, free, fast,
  testable and debuggable (matched signals are recorded). The interfaces allow model-based
  classifiers later.
- **Official SDKs for providers.** Less custom HTTP code to maintain; adapters stay thin.
- **No fake features.** Anything not implemented is labelled with the milestone that adds it,
  both in the UI and in the model’s instructions.
