# EZO roadmap

This is the **only** roadmap. Phase names here are the ones used in the code
(`apps/api/src/ezo_api/agents/catalog.py`, `apps/api/src/ezo_api/maturity.py`; a test keeps
them in sync) and in [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md).

Phase numbers follow the owner's *Universal Professional AI Robot* master prompt (2026-10-18):
Phase 1 Language Coach, Phase 2 Visual Agent, Phase 3 OCR + EZO Office, … Phase 14 optional
Ruflo. Older records in IMPLEMENTATION_STATUS keep the names they had when they were written
(there the Language Coach was "Phase 5" and the Visual Agent "Phase 6").

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

### Phase 1 — Language Coach + IELTS — alpha
- LanguageCoachAgent with persistent sessions, turns, metrics, mistakes, goals, vocabulary
  (migration 0004); an active session keeps learner answers with the coach
- Modes: free conversation, IELTS-style speaking (Parts 1–3, original questions, *estimated*
  bands), teacher, grammar, vocabulary, debate, job interview, travel, business English
- CEFR adaptation, recurring-mistake practice without nagging, feedback after the session,
  report artifact, progress answers from stored facts, goals
- Exact computed metrics (incl. words per minute from measured voice time); pronunciation
  only transcript-assisted and excluded from bands; licensed knowledge via the user's own files
- “Til mashg'ulotlari” page; details in [docs/LANGUAGE_COACH.md](docs/LANGUAGE_COACH.md)

### Phase 2 — Visual Agent — alpha
- `ImageProvider` / `ImageEditProvider` with OpenAI and Gemini adapters; model IDs, quality
  and limits are configuration; fallback that never retries a declined request
- Every image re-encoded and checked (format allowlist, pixel cap, metadata stripped)
- VisualAgent: images, hero and product visuals, edits (conversation image or upload),
  diagrams, social graphics, logo concepts with variants — all versioned image artifacts with
  provider, model, prompt and dimensions
- Text is always drawn by EZO (diagrams, social graphics, logo sheets); without a provider the
  picture is an abstract, clearly labelled placeholder and nothing is claimed
- PresentationAgent: generated images on hero slides (per-deck limit), reused on edits;
  details in [docs/VISUAL_AGENT.md](docs/VISUAL_AGENT.md)

### Orchestration foundation — experimental
- `OrchestrationProvider` interface, native mission runner (in memory), deterministic
  complexity routing, approval gates, Ruflo security boundary and audit
- Not started from chat yet (see Phase 6)

## Next (in this order)

### Phase 3 — OCR + EZO Office ← current (alpha, partially complete — 2026-10-18)
- **Done:** local Tesseract OCR (uzb, uzb_cyrl, rus, eng) for scans and photos with page
  numbers, line boxes, engine confidence (shown as an engine score), orientation and
  deskew; OCR in ingestion and citations; scan → editable / layout Word and searchable PDF
- **Done:** offline PDF engine: merge, split, delete / extract / move / rotate pages,
  orientation, image ↔ PDF, page numbers, watermark, header/footer, lossless compression,
  metadata cleanup, inspect, page-level compare; chat attachments; uz/ru/en requests
- **Done:** DOCX edits in place that keep formatting (runs, styles, numbering, tables,
  images, headers/footers, hyperlinks), real tracked changes on request, find-and-replace
- **Done:** tables → Excel (Word exact; PDF and scans detected), spreadsheet operations
  (sort, filter, duplicates, totals, group-by) computed by EZO
- **Done:** long documents processed completely (section-aware parts, map-reduce
  summaries, resumable cache, whole-file search for questions); the 40,000-character
  limit is gone
- **Not yet:** XLSX → PDF, editing Word footnotes/comments/charts, LibreOffice in the
  Docker image (PDF exports of DOCX/XLSX), handwriting OCR, an LLM planner for sheet
  operations, a document-viewer UI with page thumbnails beyond the first page

### Phase 4 — Education, academic research and career
- EducationAgent: lesson packages (plan, timing, lecture notes, PPTX, quiz, homework,
  rubric, handout), syllabus and assessment tools, level adaptation
- AcademicResearchAgent: research questions, literature, methodology, citations (APA, MLA,
  Chicago, Harvard, IEEE) without invented sources or data; academic-integrity rules
- CareerAgent: reusable master profile, CV, cover and motivation letters, interview practice;
  never invents achievements

### Phase 5 — Durable tasks, jobs and worker
- Persistent Task / Job / JobEvent / JobArtifact / JobApproval, `services/worker` with a real
  queue (Redis), recovery after restarts; chat never depends on the worker being up
- Real schedules for personal automations; `S3StorageProvider`, backups and restore

### Phase 6 — Persistent native missions
- Mission tables + migration, missions started from chat for complex requests, progress
  (“3/5 steps”), approval cards for external-impact actions

### Phase 7 — Uzbekistan government and legal intelligence
- **Foundation done early (experimental, 2026-10-18):** `OfficialSourceConnector` framework,
  legal documents with revisions (migration 0005), rate-limited resumable sync, live
  verification, LegalResearchAgent, LEX.UZ proof-of-concept connector — **off by default,
  live access not yet verified**; see [docs/OFFICIAL_SOURCES.md](docs/OFFICIAL_SOURCES.md)
- Next: verify LEX.UZ live with the owner's permission; access reviews and connectors for
  president.uz, E-qaror, gov.uz and ministry/education sites; a verified change feed;
  scheduled re-checks (needs Phase 5 jobs); publication/effective dates

### Phase 8 — Realtime voice
- Streaming STT → streaming response → streaming TTS, barge-in, turn detection, low latency;
  stronger pronunciation analysis for the Language Coach

### Phase 9 — Developer Agent + website builder
- Sandboxed repository tools (no unrestricted shell), approvals for push/deploy/destructive
  changes, inspect → reproduce → patch → test → lint → typecheck → build → diff → report
- OpenCode evaluated as an optional, isolated execution backend only
  ([docs/OPENCODE_INTEGRATION_PLAN.md](docs/OPENCODE_INTEGRATION_PLAN.md)); not installed

### Phase 10 — Data Analyst
- DataAnalystAgent: computed (never guessed) statistics, anomalies, trends, forecasts where
  appropriate, charts, dashboards, reports

### Phase 11 — Browser Agent
- Approved web actions (navigate, fill forms, download); approval before submitting,
  publishing, paying or changing accounts

### Phase 12 — Video / Motion
- StoryProject → scenes → visuals → narration → timeline → render → video artifact
  (OpenMontage only as an optional external AGPL service; licences re-checked first)

### Phase 13 — Business
- BusinessAgent: idea, competitor and market analysis, pricing, unit economics, SWOT, pitch;
  every number marked as source-backed fact, estimate or assumption

### Phase 14 — optional Ruflo provider
- Only after native missions, approvals, tool permissions and the developer sandbox are
  mature; see [docs/RUFLO_INTEGRATION_PLAN.md](docs/RUFLO_INTEGRATION_PLAN.md). Off by default.

## Known limitations (current)

- Intent and language detection are rule-based (transparent, can misread unusual phrasing).
- Semantic search and semantic memory need an OpenAI or Gemini key for embeddings; without one
  EZO uses keyword search and says so.
- Images and scanned PDFs are stored but not read (no OCR yet).
- Image generation needs an OpenAI or Gemini key; EZO-drawn diagrams work without one.
- Ingestion runs in the API process (resumed at startup); no separate worker yet.
- Voice is turn-by-turn; realtime voice is Phase 8.
- The rate limiter is in memory (one API process).
- Single-owner authentication; no multi-user accounts.
- Some API status/error texts are English-only (new texts are added in uz/en/ru).
- Default model names in `apps/api/config/models.toml` and the image model settings must be
  kept current.
- Not yet: Qdrant vector store, S3 storage, model-based reranker (interfaces exist).
