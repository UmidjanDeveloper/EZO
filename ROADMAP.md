# EZO roadmap

EZO is built in milestones. Each milestone ends with lint, type-check, tests and a production
build passing (`python scripts/ezo.py test --e2e` and `python scripts/ezo.py build`).

Legend: ✅ done · 🔜 next · ⏳ planned

## ✅ Milestone 1 — Foundation

- [x] Monorepo (pnpm workspace + uv project), one-command Docker start, `scripts/ezo.py`
- [x] FastAPI backend, PostgreSQL, Alembic migrations, UUID keys, portable schema (SQLite for tests)
- [x] Authentication abstraction (local owner / token mode)
- [x] `ModelProvider` interface + Anthropic, OpenAI, Gemini adapters + offline mode
- [x] Configurable model routing (`models.toml`) with provider fallback
- [x] EzoCore pipeline (language, intent, agent selection, context, memory, plan, prompt,
      generation, verification, persistence) with safe execution traces
- [x] Agent catalog with availability; GeneralAgent (also covers unavailable agents honestly)
- [x] Personality engine (TOML profile, context modes, humor levels)
- [x] Conversations, projects, streaming chat (SSE), stop generation
- [x] Memory: importance scoring, sensitivity filter, profile/project memory, inspect/delete UI
- [x] Security basics: rate limiting, input limits, audit log, security headers
- [x] Web UI: only the EZO robot + conversation history; type or talk; projects, memory and
      settings behind small icons; uz/en/ru, dark/light, mobile
- [x] Voice conversation with the browser’s speech recognition and synthesis (hands-free loop,
      tap to interrupt, spoken-style replies via `channel: "voice"`)
- [x] Tests: unit, integration (SQLite + PostgreSQL), browser end-to-end; CI workflow
- [x] Docs: README, SETUP_WINDOWS, ARCHITECTURE, TROUBLESHOOTING

## ✅ Milestone 2 — Knowledge, files and research

- [x] `StorageProvider` interface + local filesystem implementation (validated keys, atomic writes)
- [x] Upload validation: extension allow-list + content sniffing, size limit (413), zip-bomb
      limits, filename sanitising, path-traversal safety, SHA-256 duplicate detection
- [x] Parsers: PDF, DOCX, XLSX, CSV, TXT, Markdown, HTML (web pages); images marked “needs OCR”
- [x] Ingestion pipeline: fetch → parse → normalise → metadata → chunk → embed → index → revisions
      (background runner with persisted status, resumes after restart; never overwrites a revision)
- [x] `VectorStore` interface with pgvector (PostgreSQL) and a built-in local store; vector,
      keyword (PostgreSQL full-text / BM25), hybrid (RRF), metadata/project filters, reranker hook
- [x] Embeddings through `ModelProvider.embed` (OpenAI / Gemini), one active model, model-keyed vectors
- [x] Retrieval with relevance gates and numbered citations (file, page, revision, URL, date,
      reliability); citation verification removes invented numbers
- [x] Entities + migration 0002: KnowledgeSource, KnowledgeDocument, DocumentRevision,
      KnowledgeChunk, VectorEntry, ToolCall
- [x] Tool interface + registry (validation, permissions, timeouts) + logged tool calls
- [x] ResearchAgent: query planning, file + web search (Claude web search or Tavily),
      primary/official-source preference, page reading via SSRF-safe fetcher, dated citations
- [x] Semantic memory retrieval (hybrid: semantic + lexical + importance + recency + project)
- [x] UI: Files page (drop/upload, add link, status, errors, versions, previews, re-read,
      delete), paperclip in the composer, sources under answers, live activity states
- [ ] Deferred (not faked): Qdrant implementation (interface ready), S3 storage provider
      (interface ready), OCR for images/scans (Milestone 4), model-based reranker

## Open-source integration track (from the integration prompt)

Licences reviewed in [docs/OPEN_SOURCE_AUDIT.md](docs/OPEN_SOURCE_AUDIT.md). No external code is
copied; AGPL projects are optional separate services.

- [x] Phase 1 — EZO presence: original orb with idle, listening, thinking, speaking, searching,
      reading, coding, creating, working, completed and error states (ideas from APEX-UI, MIT)
- [x] Phase 2 — voice provider interfaces (STT / TTS; realtime interface only) + OpenAI voice
      + optional VoiceStudio service over its HTTP API (`voice` Docker profile); browser voice
      stays as fallback; audio never stored

## Current development order (from the next-development prompt)

- [x] **Phase 3 — Artifact system + StoryProject foundation**
  - [x] `Artifact` + immutable `ArtifactVersion` (migration 0003); content-addressed storage
        through the existing StorageProvider; MIME types decided by EZO; owner-only access
  - [x] Edit → new version, restore → new version, identical content → no new version,
        download (attachment, `nosniff`, sandbox CSP), rename, confirmed delete, audit log
  - [x] “Yaratilganlar / Created” page (filter, versions, preview, edit, restore, download,
        rename, delete) and artifact cards inside conversations; “Save” under any answer
  - [x] `StoryProject` / `StoryScene` / `StoryAsset` / `StoryNarration` / `StoryTimeline` with
        CRUD, scene ordering and narration-aware timeline planning (`/api/stories`)
- [x] **Phase 4 — DocumentAgent + PresentationAgent**
  - [x] Format services outside the agents: DOCX (python-docx), PDF (reportlab, bundled
        Liberation Sans), XLSX/CSV (openpyxl, formula-injection guard), Markdown/TXT, diff
  - [x] `OCRProvider` interface (no fake OCR: scans stay `needs_ocr`)
  - [x] DocumentAgent: create, summarize, translate, proofread, rewrite, formal style, compare,
        spreadsheet analysis (computed facts) and creation, convert (works offline)
  - [x] Edits → new artifact version (EZO documents) or a derived artifact (uploads), with a
        change summary and diff statistics; the original is never changed
  - [x] Own slide engine: 24 layouts, 5 themes, text fitted with real font metrics, native
        PPTX charts/tables/bullets/notes, PDF, web version, PNG previews
  - [x] Layout QA (overflow, tiny text, bounds, chart data, missing tables, duplicate titles,
        density) with one model repair round; PPTX re-opened before it is reported
  - [x] PresentationAgent: sources → narrative → deck → QA → artifact + StoryProject; sources
        slide; follow-up edits become new versions
  - [x] Artifact exports (PDF, web, Word, previews…) with downloads and thumbnails in the UI
- [ ] Optional orchestration (Ruflo / native missions) — architecture and audit prepared, see
      [`docs/RUFLO_INTEGRATION_PLAN.md`](docs/RUFLO_INTEGRATION_PLAN.md); execution comes after
      the creative and developer foundations
- [ ] Phase 5 — LanguageCoachAgent + IELTS-style speaking simulator (estimated bands)
- [ ] Phase 6 — VisualAgent (ImageProvider / ImageEditProvider; open-higgsfield as idea source only)
- [ ] Phase 7 — Video / motion studio (MediaProductionProvider; optional OpenMontage worker;
      Remotion licence re-checked first)
- [ ] Phase 8 — Uzbekistan government knowledge (LegalResearchAgent + lex.uz / president.uz /
      e-qaror / gov.uz connectors)
- [ ] Phase 9 — DeveloperAgent + website builder (sandboxed repository tools)
- [ ] Later — advanced tasks, background worker, business workflows; optional REA binary
      analysis (off by default)

## ⏳ Milestone 3 — Language

- [ ] LanguageCoachAgent: free conversation, teacher, grammar, vocabulary, debate,
      job interview, travel and business roleplay
- [ ] IELTS-style speaking simulator (three parts, four criteria; clearly *not* an official examiner)
- [ ] Mistake tracking during sessions, feedback after sections
- [ ] LanguageSession and LanguageMetric storage, progress reports and graphs
- [ ] CEFR levels; reuse of past mistakes in exercises
- [ ] Licensed language knowledge base (official IELTS descriptors and samples, OER)
- [ ] Realtime voice interfaces (provider-agnostic) prepared

## ⏳ Milestone 4 — Creative studio

- [ ] Artifact system (versions, files, metadata, edit later)
- [ ] DocumentAgent: PDF / DOCX / XLSX / CSV read & create, OCR provider interface
- [ ] PresentationAgent: audience → narrative → slide architecture → content → visuals → QA
- [ ] PPTX export (PptxGenJS), PDF and web presentations; Remotion for motion
- [ ] Presentation design knowledge base (own layouts, colour systems, rules)
- [ ] VisualAgent interface (image generation providers, provenance metadata)

## ⏳ Milestone 5 — Government knowledge

- [ ] Connectors: LexUzConnector, PresidentUzConnector, EqarorConnector, GovUzConnector
- [ ] Legal metadata (number, authority, type, dates, status, versions, relations)
- [ ] Revision tracking with content hashes; never overwrite history silently
- [ ] Background synchronisation (worker + Redis), robots/terms/rate-limit compliance
- [ ] Current-law retrieval with aggressive metadata filtering; live re-check when stale
- [ ] Admin sync screen (last sync, documents indexed/changed, errors)
- [ ] LegalResearchAgent

## ⏳ Milestone 6 — Developer

- [ ] DeveloperAgent with repository tools (read_file, write_file, search_code, git_status,
      git_diff, run_tests, run_command)
- [ ] Sandboxed command execution; explicit permission for dangerous actions
- [ ] Test/lint/build workflow, commit and pull-request preparation
- [ ] Website/app builder workflow

## ⏳ Milestone 7 — Realtime voice

- [ ] Server-side realtime voice providers (replacing the browser Web Speech API used since M1):
      microphone → VAD → speech recognition → streaming response → TTS
- [ ] Interruption, low latency, transcript stored separately from audio
- [ ] Full-screen speaking UI (timer, waveform, goal, transcript) and session reports
- [ ] Pronunciation feedback

## ⏳ Milestone 8 — Advanced agent workflows

- [ ] Task and Job entities (queued → planning → running → waiting_for_user → completed/failed/cancelled)
- [ ] Background worker (`services/worker`) with persisted progress and UI status
- [ ] Multi-agent orchestration (LangGraph if the explicit pipeline is no longer enough)
- [ ] BusinessAgent (market research with retrieved data, labelled estimates)
- [ ] Complex research workflows

## Known limitations after Milestone 2

- Intent and language detection are rule-based (transparent, but can misread unusual phrasing;
  you can still talk normally — the GeneralAgent answers everything).
- Semantic search and semantic memory need an OpenAI or Gemini key (embeddings); without one,
  EZO falls back to keyword search and says so.
- Images and scanned PDFs are stored but not read (OCR is Milestone 4).
- Ingestion runs in the API process (asyncio tasks, resumed at startup); a separate worker
  with Redis arrives in Milestone 8.
- Some status/error texts from the API are in English while the interface is uz/en/ru.
- Voice is turn-by-turn (record until a pause → transcribe → answer → speak, tap to
  interrupt). Server voice needs `OPENAI_API_KEY` or the optional VoiceStudio service;
  otherwise the browser’s speech services are used (not Firefox; Uzbek voices depend on the
  device). Realtime streaming voice is Milestone 7.
- The rate limiter is in-memory (one API process). Redis arrives with the worker.
- Single-owner authentication; multi-user accounts are not implemented.
- Default model names in `models.toml` must be kept current with the providers’ model lists.
