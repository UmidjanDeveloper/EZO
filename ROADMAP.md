# EZO roadmap

This is the **only** roadmap. Phase names here are the ones used in the code
(`apps/api/src/ezo_api/agents/catalog.py`, `apps/api/src/ezo_api/maturity.py`; a test keeps
them in sync) and in [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md).

Maturity labels: **planned** (not built) · **experimental** (works in tests, may change) ·
**alpha** (usable end to end, young) · **beta** · **stable**. Nothing in EZO is beta or stable yet.

A phase is done only when the checks in [Verification](IMPLEMENTATION_STATUS.md#verification-convention)
pass: CI (lint, types, SQLite and PostgreSQL tests, migrations, web build, Playwright, Docker
images) plus the extended local checks listed for that phase.

## Done

### Foundation — alpha
- Monorepo (pnpm + uv), Docker Compose, `scripts/ezo.py`, CI
- FastAPI, PostgreSQL (SQLite for tests), Alembic, authentication (local owner / token)
- `ModelProvider` (Anthropic, OpenAI, Gemini, offline notice), routing with fallback (`models.toml`)
- EzoCore pipeline: language, intent, agent selection, context, memory, plan, prompt,
  generation, verification, persistence, execution traces (no hidden reasoning stored)
- Personality engine; conversations, projects, streaming chat; memory with sensitivity filter
- Security basics: rate limiting, input limits, audit log, security headers
- Web UI: the EZO orb + conversation history; uz/en/ru, dark/light, mobile

### Knowledge — alpha
- Storage provider (local), validated uploads, parsers (PDF, DOCX, XLSX, CSV, TXT, MD, HTML)
- Ingestion with revisions, vector stores (pgvector / local), hybrid retrieval, citations
- Tool registry with logged calls; ResearchAgent (files + web, ranked sources, dated citations)
- Files page, paperclip upload, sources under answers

### Voice — alpha
- Presence: the orb shows real activity states only
- Turn-by-turn voice: STT/TTS provider interfaces, OpenAI voice, optional VoiceStudio service
  (separate AGPL container, `voice` profile), browser fallback; raw audio is never stored

### Artifacts — alpha
- Artifacts with immutable versions, restore as a new version, exports, safe downloads
- “Yaratilganlar / Created” page and artifact cards in chat
- Story projects (scenes, narration, timeline) — **experimental**, API only

### Documents — alpha
- Format services: DOCX, PDF, XLSX/CSV, Markdown/TXT, diff; `OCRProvider` interface only
- DocumentAgent: create, summarize, translate, proofread, rewrite, formal style, compare,
  spreadsheet analysis and creation, convert (offline)

### Presentations — alpha
- Own slide engine: 24 layouts, 5 themes, font-metric text fitting, native PPTX charts and
  tables, PDF, web version, PNG previews, layout QA with one repair round
- PresentationAgent with sources slide, StoryProject link and edits as new versions

### Sprint 0 — Stabilization
- One roadmap, catalog phases and maturity labels, verification convention (CI vs local)
- Docker images built and smoke-tested in CI, dependency audits, `docs/SECURITY.md`,
  Git workflow and licence decision documented for the owner

### Phase 5 — Language Coach + IELTS — alpha
- LanguageCoachAgent with persistent sessions, turns, metrics, mistakes, goals, vocabulary
  (migration 0004); an active session keeps learner answers with the coach
- Modes: free conversation, IELTS-style speaking (Parts 1–3, original questions, *estimated*
  bands), teacher, grammar, vocabulary, debate, job interview, travel, business English
- CEFR adaptation, recurring-mistake practice without nagging, feedback after the session,
  report artifact, progress answers from stored facts, goals
- Exact computed metrics (incl. words per minute from measured voice time); pronunciation
  only transcript-assisted and excluded from bands; licensed knowledge via the user's own files
- “Til mashg'ulotlari” page; details in [docs/LANGUAGE_COACH.md](docs/LANGUAGE_COACH.md)

### Orchestration foundation — experimental
- `OrchestrationProvider` interface, native mission runner (in memory), deterministic
  complexity routing, approval gates, Ruflo security boundary and audit
- Not started from chat yet (see *Missions* below)

## Next (in this order)

### Phase 6 — Visual Agent ← current
- `ImageProvider` / `ImageEditProvider` (OpenAI, Gemini, later local), configurable models
- Image generation and editing, diagrams, social graphics, logo concepts, product visuals
- PresentationAgent requests visuals; honest placeholders when no provider is available

### Phase 6.5 — OCR + document fidelity + long documents
- Real `OCRProvider` implementations with page numbers, confidence and text blocks
- DOCX editing that preserves formatting; chunk-aware map/reduce for long documents
  (replaces the current 40,000-character limit)

### Infrastructure — durable jobs
- Persistent Task / Job / JobEvent / JobArtifact / JobApproval, `services/worker` with a real
  queue (Redis), recovery after restarts; chat never depends on the worker being up
- `S3StorageProvider`, backups and restore procedure

### Missions — persistent native orchestration
- Mission tables + migration, missions started from chat for complex requests, progress
  (“3/5 steps”), approval cards for external-impact actions

### Phase 8 — Uzbekistan government knowledge
- LegalResearchAgent; LexUz, President.uz, E-qaror, Gov.uz connectors
- Versioned legal documents (never overwritten), currentness checks, admin sync status

### Phase 7 — Realtime voice
- Streaming STT → streaming response → streaming TTS, barge-in, turn detection, low latency;
  stronger pronunciation analysis for the Language Coach

### Phase 9 — Developer Agent + website builder
- Sandboxed repository tools (no unrestricted shell), approvals for push/deploy/destructive
  changes, inspect → reproduce → patch → test → lint → typecheck → build → diff → report

### Video / Motion
- StoryProject → scenes → visuals → narration → timeline → render → video artifact
  (OpenMontage only as an optional external AGPL service; licences re-checked first)

### Business
- BusinessAgent: idea, competitor and market analysis, pricing, unit economics, SWOT, pitch;
  every number marked as source-backed fact, estimate or assumption

### Last — optional Ruflo provider
- Only after native missions are proven stable; see
  [docs/RUFLO_INTEGRATION_PLAN.md](docs/RUFLO_INTEGRATION_PLAN.md). Off by default.

## Known limitations (current)

- Intent and language detection are rule-based (transparent, can misread unusual phrasing).
- Semantic search and semantic memory need an OpenAI or Gemini key for embeddings; without one
  EZO uses keyword search and says so.
- Images and scanned PDFs are stored but not read (no OCR yet).
- Ingestion runs in the API process (resumed at startup); no separate worker yet.
- Voice is turn-by-turn; realtime voice is Phase 7.
- The rate limiter is in memory (one API process).
- Single-owner authentication; no multi-user accounts.
- Some API status/error texts are English-only (new texts are added in uz/en/ru).
- Default model names in `apps/api/config/models.toml` must be kept current.
- Not yet: Qdrant vector store, S3 storage, model-based reranker (interfaces exist).
