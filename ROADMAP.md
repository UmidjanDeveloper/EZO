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

## Current engineering priority — controlled Student foundation

- Native production processing remains **BLOCKED** pending a verified isolated runtime
  for D4/D6/D7. The coordinated implementation fails closed and removes OCR/Office
  binaries from production while retaining fixture regression coverage.
- Durable stored-text jobs, SQL pagination and the controlled Student text-reading API
  are implemented for independent review; PDF/DOCX/EPUB Student ingestion remains blocked.
  See [current architecture and gates](docs/P0_P1_CONTROLLED_STUDENT_REVIEW.md).
- No deployment, paid infrastructure, real provider use or K4–K7 is authorized here.

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

### Professional writing — alpha
- `writing/`: 30 document types (ariza, xizmat xati, bayonnoma, buyruq/qaror loyihasi,
  hisobot, ma'ruza, press-reliz, CV, motivatsion xat, tadqiqot taklifi…) with fields and
  structure; writing modes; Uzbek style rules and a deterministic style check
- Drafts validated: unknown details become placeholders, numbers/dates not given by the
  user are flagged, signing/approval claims are flagged; official papers marked QORALAMA
- Official-layout DOCX (+ PDF via LibreOffice, Markdown, text); templates without a model;
  organization profiles (letterhead, contacts, house style, preferred terms) in Settings

### Translation — alpha
- `translation/`: text translation (uz Latin, uz Cyrillic, ru, en) with domain styles;
  Uzbek Latin ↔ Cyrillic by fixed rules without a model (text, Word files in place)
- Documents reuse the existing pipeline: Word in place (DOCX fidelity), other files through
  Markdown, long files part by part; Cyrillic output converted by EZO, not the model
- Terminology memory (glossary, also per organization; migration 0009), used in prompts and
  checked afterwards; quality checks for numbers, dates, links, names, missing and
  untranslated paragraphs, script; bilingual two-column Word files
- Turn-based voice interpretation API (speech → text → translation → speech); simultaneous
  interpretation is not built (interface only)

### Phase 4 — Education, academic research and career — alpha (2026-10-19, Stage D)
- Teaching and study materials: lesson packages (Word + Excel + slides), quizzes with an
  EZO-built answer key, syllabi, rubrics, study plans, defense and interview questions;
  checks for answers, timing, weights and points; templates without a model
- Academic: OpenAlex literature search, research plans that cite only found works,
  reference lists by EZO in APA, MLA, Chicago, Harvard, IEEE and GOST; pasted reference
  lists formatted with every field verified against the text
- Career: career profile (migration 0010) in Settings, CV built exactly from it, letters
  and interview questions grounded in it
- Not yet: grade books, online tests, profile translation, live OpenAlex verification

### Government work mode — E1 organization profiles alpha (2026-10-19, Stage E)
- E1 (alpha): standard formatting, logo, approved Word templates with the `{{matn}}`
  marker, example documents as style references, terminology, ZIP export, deletion with
  files (migration 0011); used by official letters, other documents ("blankasida") and
  presentations
- Next: E2 secretary (minutes and task registers from notes, documents and — only with a
  real transcription provider — audio), E3 citizen appeals, E4 reports

### Knowledge OS — K1, K2 & K3 done (2026-10-19, Knowledge OS & SkillForge prompt)
- K1 (done): named knowledge libraries; learned sources — documentation websites
  (one site and folder, robots.txt, polite pacing, page/depth/size/time budgets), GitHub
  repositories (API metadata, licence, commit, file tree; README, docs, manifests, API
  specs, examples and entry points read as text; raw-file fallback), PyPI and npm packages
  (registry facts, README, linked documentation site); prompt-injection passages flagged
  and audit-logged; licence assessment for commercial use; migration 0012; chat ("… ni
  o'rgan", "o'rgangan manbalaringni ko'rsat") and the Knowledge page
- K2 (done): library-scoped retrieval in chat, citations with version/license/last_checked_at,
  freshness indicators (current, changed, not_recently_checked), turn continuity, library switching,
  ownership validation (no cross-user/cross-library leak), no silent fallback on empty/irrelevant results;
  migration 0013.
- K3 (done): capability analyzer service, 10-point structured proposals, EZO tool and agent registry
  comparison, evidence grading (directly_supported/inferred/unverified), cross-source deduplication,
  prompt-injection containment, read-only status guarantee, library & source capability APIs,
  chat analyzer intent, web UI capability inspection panel.
- Next: K4 secure sandbox (hard prerequisite for running any generated
  code); K5 skill builder and verification; K6 skill registry and runtime; K7 updates
- Nothing read from a source is executed or installed; no skill exists before K4–K6

### Orchestration foundation — experimental
- `OrchestrationProvider` interface, native mission runner (in memory), deterministic
  complexity routing, approval gates, Ruflo security boundary and audit
- Not started from chat yet (see Phase 6)

## Universal professional agent master prompt (2026-10-18) — stage map

The owner's master prompt orders work as stages; they map onto this roadmap:
A Office completion → Phase 3 (done) · B Professional writing (done, alpha) ·
C Translation (done, alpha) · D Education & career → Phase 4 (done, alpha) · E Government work mode (E1
organization profiles done, alpha; E2–E4 next) · F Official knowledge → Phase 7 · G Press secretary / Telegram ·
H Durable missions → Phases 5–6 · I Advanced (voice, browser, developer, data, video,
business) → Phases 8–13 · J single-user beta · K SaaS (deferred until the owner approves).

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
- **Done (2026-10-18, Stage A):** Word/Excel → PDF with LibreOffice (in the Docker image
  and CI), export regression fixtures, conversion limits
- **Not yet:** editing Word footnotes/comments/charts, handwriting OCR, an LLM planner for
  sheet operations, a document-viewer UI with page thumbnails beyond the first page

### Phase 5 — Durable tasks, jobs and worker
- Persistent Task / Job / JobEvent / JobArtifact / JobApproval, `services/worker` with a real
  durable queue, recovery after restarts; chat never depends on the worker being up.
  Student P1 proposes PostgreSQL leases/fencing first to avoid a mandatory new Redis
  service; record/review the queue ADR before implementation. Redis remains an option
  when measured requirements justify it, rather than existing functionality
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
- Images and scanned PDFs use installed Tesseract OCR; without the engine the API
  reports that OCR is unavailable. OCR confidence is an engine score, not calibrated accuracy.
- Image generation needs an OpenAI or Gemini key; EZO-drawn diagrams work without one.
- Ingestion runs in the API process (resumed at startup); no separate worker yet.
- Voice is turn-by-turn; realtime voice is Phase 8.
- The rate limiter is in memory (one API process).
- Single-owner authentication; no multi-user accounts.
- Some API status/error texts are English-only (new texts are added in uz/en/ru).
- Default model names in `apps/api/config/models.toml` and the image model settings must be
  kept current.
- Not yet: Qdrant vector store, S3 storage, model-based reranker (interfaces exist).
