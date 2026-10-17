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

## 🔜 Milestone 2 — Knowledge

- [ ] File storage abstraction (local filesystem; S3-compatible for production)
- [ ] Document upload with validation (type, size, filename sanitising, path-traversal safety)
- [ ] Ingestion pipeline: fetch → parse → normalise → metadata → chunk → embed → index → revisions
- [ ] `VectorStore` interface with pgvector and Qdrant implementations
- [ ] Embeddings through `ModelProvider.embed` (OpenAI / Gemini)
- [ ] Hybrid retrieval (vector + keyword), metadata filters, optional reranking
- [ ] Citations with source metadata; citation verification
- [ ] Entities: KnowledgeSource, KnowledgeDocument, KnowledgeChunk, DocumentRevision, ToolCall
- [ ] Tool interface + registry + logged tool calls
- [ ] ResearchAgent (basic): web search tool, official-source preference, citations
- [ ] Semantic memory retrieval (embeddings replace lexical relevance)

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

## Known limitations after Milestone 1

- Intent and language detection are rule-based (transparent, but can misread unusual phrasing;
  you can still talk normally — the GeneralAgent answers everything).
- Memory relevance is lexical until embeddings arrive in Milestone 2.
- No tool calling, web access or file upload yet. Voice uses the browser’s speech services
  (not Firefox; Uzbek voices depend on the device).
- The rate limiter is in-memory (one API process). Redis arrives with the worker.
- Single-owner authentication; multi-user accounts are not implemented.
- Default model names in `models.toml` must be kept current with the providers’ model lists.
