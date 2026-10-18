# EZO implementation status

What is **verified** to work, how it was verified, and what is not done. Nothing is listed as
working unless it was tested. The one roadmap is [ROADMAP.md](ROADMAP.md).

## Verification convention

Two kinds of results are reported, **never mixed**:

1. **CI verified** — what GitHub Actions ran on a specific commit (workflow *CI*: jobs *API*,
   *Web* and *Docker*). This is the authoritative number. Every CI job ends with a
   `scripts/test_report.py` table (collected / passed / failed / skipped and every skip
   reason) in the job log and the run summary. Quote that table, with the run number and
   commit.
2. **Extended local verification** — checks CI cannot run, listed by name: LibreOffice
   opening generated files (CI has no LibreOffice, so 3 tests skip there), Docker builds in
   the development sandbox, live provider calls, manual UI checks. These are reported as
   "local, not in CI".

Why the numbers differ between environments (all expected):

| Test | SQLite (CI) | PostgreSQL (CI) | Local with LibreOffice |
|---|---|---|---|
| pgvector store test | skipped (needs PostgreSQL + pgvector) | runs | runs on PostgreSQL |
| LibreOffice open/convert tests (3) | skipped (no LibreOffice on the runner) | skipped | run |

Produce the same table locally:

```bash
cd apps/api
uv run pytest -q -rs --junitxml=reports/sqlite.xml
EZO_TEST_DATABASE_URL=postgresql://ezo:ezo@localhost:5432/ezo_test \
  uv run pytest -q -rs --junitxml=reports/postgres.xml
cd ../.. && python3 scripts/test_report.py \
  "API · SQLite=apps/api/reports/sqlite.xml" "API · PostgreSQL=apps/api/reports/postgres.xml"
```

Test counts are not a quality score: a phase is judged by which failure modes its tests cover
(listed per phase below), not by how many tests exist.

## Current capabilities

Phase numbers follow the 2026-10-18 master prompt (see ROADMAP.md); the history below keeps
the names used when each record was written.

Source of truth: `apps/api/src/ezo_api/maturity.py` and the agent catalog (also returned by
`GET /api/status` as `agents` and `features`). A test keeps them consistent with ROADMAP.md.

| Capability | Phase | Maturity |
|---|---|---|
| EzoCore chat, routing, personality, memory | Foundation | alpha |
| Files, knowledge base, citations; ResearchAgent | Knowledge | alpha |
| Turn-by-turn voice, orb presence states | Voice | alpha |
| Artifacts with versions and exports | Artifacts | alpha |
| Story projects (API only) | Artifacts | experimental |
| DocumentAgent + document formats | Documents | alpha |
| PresentationAgent + slide engine | Presentations | alpha |
| Native missions (in memory, not in chat) | Orchestration foundation | experimental |
| LanguageCoachAgent, IELTS-style simulator, progress | Phase 1 | alpha |
| VisualAgent: images, edits, diagrams, social graphics, logos, slide images | Phase 2 | alpha |
| OCR + EZO Office (PDF tools, DOCX fidelity, long documents) | Phase 3 | planned |
| Education, academic research and career agents | Phase 4 | planned |
| Durable tasks / jobs / worker | Phase 5 | planned |
| Persistent missions in chat | Phase 6 | planned |
| LegalResearchAgent | Phase 7 | planned |
| Realtime voice | Phase 8 | planned |
| DeveloperAgent + website builder | Phase 9 | planned |
| DataAnalystAgent | Phase 10 | planned |
| BrowserAgent | Phase 11 | planned |
| Video / motion | Phase 12 | planned |
| BusinessAgent | Phase 13 | planned |
| Ruflo provider | Phase 14 | planned (off by default) |

Planned agents are never shown as working: the GeneralAgent answers and states the
limitation.

## Latest verified baseline

**CI verified** — run #24 (CI), commit `a78fe8f`, all jobs green:

| Suite | Collected | Passed | Failed | Skipped | Skip reasons |
|---|---:|---:|---:|---:|---|
| API · SQLite | 385 | 381 | 0 | 4 | 1 needs PostgreSQL + pgvector; 3 LibreOffice not installed |
| API · PostgreSQL | 385 | 382 | 0 | 3 | 3 LibreOffice not installed |
| Web unit (Vitest) | 41 | 41 | 0 | 0 | — |
| Shared unit (Vitest) | 10 | 10 | 0 | 0 | — |
| Playwright e2e | 22 | 22 | 0 | 0 | — |

Also green in that run: ruff, format check, mypy, `alembic check` on PostgreSQL, ESLint,
TypeScript, the web production build and the Docker job (Compose config including the
`voice` profile, API and web image builds, API container migrates and answers
`/api/health`, web container serves `/`).

**Extended local verification** (not in CI): the 3 LibreOffice tests pass (SQLite 384 passed
+ 1 skipped; PostgreSQL 385 passed); the full Playwright suite passed locally (22); the API
Docker image was rebuilt in the sandbox and, inside the container, rendered a diagram and
built a deck with a slide image (no QA issues). Live image generation was **not** run: there
are no provider keys in this environment, so the OpenAI and Gemini adapters are verified with
SDK-shaped fakes only.

## Sprint 0 — Stabilization (2026-10-17)

**What changed**
- One authoritative ROADMAP (Done / Next in the agreed order); the old milestone structure
  is removed everywhere (docs, code comments, one user-visible OCR message).
- The agent catalog has a roadmap `phase` and a `maturity` label instead of milestone
  numbers. Availability is derived from maturity, so a planned agent can never run. A new
  `maturity.py` covers non-agent capabilities; both are exposed in `/api/status` (`agents`,
  `features`).
- Verification convention: `scripts/test_report.py` reads JUnit reports from pytest,
  Vitest and Playwright, and prints the same table in CI (job log and run summary) and
  locally (`python scripts/ezo.py test`).
- CI Docker job: Compose validation, API and web image builds, API and web smoke tests.
  Optional services (VoiceStudio) are not built.
- Security: `security.yml` (pip-audit, pnpm audit; weekly and on dependency changes),
  Dependabot (opens PRs only, minor and patch, no majors), `docs/SECURITY.md`.
- Owner documents: `docs/GIT_WORKFLOW.md` (no `main` or branch protection exists yet; exact
  steps given) and `docs/OWNER_DECISIONS.md` (EZO has no LICENSE — not chosen on the owner's
  behalf).

**Files added:** `apps/api/src/ezo_api/maturity.py`, `apps/api/tests/unit/test_catalog.py`,
`scripts/test_report.py`, `.github/workflows/security.yml`, `.github/dependabot.yml`,
`docs/SECURITY.md`, `docs/GIT_WORKFLOW.md`, `docs/OWNER_DECISIONS.md`.
**Files modified:** agent catalog, status schema and route, shared types, CI workflow,
Playwright config, `scripts/ezo.py`, `.gitignore`, ROADMAP, IMPLEMENTATION_STATUS, README,
ARCHITECTURE, TROUBLESHOOTING, `.env.example`, a few code comments.
**Database migrations:** none.

**Tests added:** catalog consistency (exactly the implemented agents are available, planned
agents have limitation notes, every phase exists in ROADMAP, unique feature keys).

**Security changes:** dependency audits and update policy, documented security model.

**User-visible changes:** none in the UI. `/api/status` returns `maturity`, `phase` and
`features`; the "needs OCR" message no longer names an obsolete milestone.

**Known limitations / not done:** branch protection and `main` need the owner. The CI
actions still run on Node 20 (GitHub forces them to Node 24 and shows a warning; no
failure). Dependabot has started scanning and may open PRs on this branch, since it is the
repository's default branch.

**How the owner can test:** open the Actions tab → latest *CI* run → each job's summary
shows the test table. `curl localhost:8000/api/status` lists agents with
`maturity`/`phase`.

## Phase 2 — Visual Agent (2026-10-18) — alpha

*(Called "Phase 6" before the 2026-10-18 renumbering.)*

**What changed**
- Image providers behind `ImageProvider` / `ImageEditProvider`: OpenAI (Images API) and
  Gemini (image output) adapters; model IDs, quality and limits are settings
  (`EZO_IMAGE_*`). `VisualService` falls back in order but never after a content-policy
  refusal, and re-encodes every returned image (format allowlist, pixel cap, metadata
  stripped).
- `VisualAgent` (alpha): images, hero and product visuals, edits of the conversation's image
  or an uploaded image, diagrams, social graphics (square / 4:5 / story / landscape), logo
  concepts with variants. One cheap `chat`-route call writes the prompt or spec; no call is
  made when a picture is needed but no provider exists.
- EZO draws all text: diagrams through the slide engine (PNG + SVG), social graphics and logo
  sheets with EZO fonts. Without a provider the picture is an abstract placeholder recorded as
  `placeholder: true` with a reason.
- Every output is a versioned `image` artifact (edits add versions) with provider, model,
  prompt, revised prompt, dimensions, quality, attempts, conversation and project; uploads
  keep a source reference.
- Presentations: new `ImageBox` primitive in PPTX/PDF/PNG/HTML; hero slides get generated
  images (`EZO_IMAGE_MAX_PER_DECK`), reused when a deck is edited; model-written image ids
  are discarded and only the user's own image artifacts are loaded; story scenes link them.
- Routing: broader uz/en/ru visual signals; "fonini ko'k qil" after an image edits it.
  `/api/status` lists `image_providers`; `visual` feature is alpha.
- Web: image preview in the chat card; artifacts page shows the preview, how it was made, or
  the placeholder notice; uz/en/ru strings.
- Roadmap renumbered to the 2026-10-18 master prompt (catalog and features follow).

**Files added:** `apps/api/src/ezo_api/visual/{base,images,openai_images,gemini_images,service,compose,kinds}.py`,
`apps/api/src/ezo_api/agents/visual.py`, `apps/api/src/ezo_api/tools/visual_tools.py`,
`apps/api/tests/unit/test_visual.py`, `apps/api/tests/integration/test_visual_agent.py`,
`apps/web/components/artifacts/VersionExports.test.ts`, `tests/e2e/specs/visual.spec.ts`,
`docs/VISUAL_AGENT.md`.
**Files modified:** slide engine (primitives, layouts, QA, build, spec, PPTX/PDF/PNG/HTML
renderers), PresentationAgent, `create_presentation`, story-from-deck, EzoCore routing,
intent rules, agent registry and catalog, `maturity.py`, settings, services, status schema
and route, test fakes and four existing tests (a planned agent is now Business, not Visual),
web artifact card/page/exports, i18n, shared types, `.env.example`, ROADMAP, README,
ARCHITECTURE, TROUBLESHOOTING, `docs/SECURITY.md`, `docs/LANGUAGE_COACH.md`.
**Database migrations:** none (`image` was already an artifact type; `alembic check` clean).

**Tests added:** 22 unit test cases (image safety: crop, re-encode, EXIF removal, non-images,
decompression bombs, downscaling; request rules; OpenAI and Gemini adapters incl. refusals;
fallback order and refusal stop; settings → providers; diagram/social/logo layouts; slide
images in every format; placeholder QA; image-id validation) and 10 integration tests
(generate + follow-up edit as version 2, no provider = no call and nothing stored, diagram
without provider, labelled social placeholder, logo variants + text edit reusing the symbol,
final refusal, upload edit, deck images generated and reused on edit, deck without provider,
status); one web unit test; one Playwright spec (2 tests).

**Security changes:** untrusted image gate (decode, allowlist, 25 MB / 40 MP, re-encode);
SVG only as a sandboxed attachment; model-written artifact ids discarded and ownership checked
before an image is embedded; refusals never routed around; per-request and per-deck limits
for paid image calls.

**User-visible changes:** ask for an image, a diagram, a social graphic or a logo in chat;
image previews in chat and on **Yaratilganlar**; picture slides in presentations.

**Known limitations:** rule-based kind/edit detection; diagrams limited to the slide engine's
flow/process/timeline layouts; no masks, upscaling or transparent exports yet; only hero
slides get generated images; image generation runs inside the chat request (durable jobs are
Phase 5); the adapters are tested with SDK-shaped fakes, not against live provider accounts
(no keys in CI). See `docs/VISUAL_AGENT.md`.

**How the owner can test:** put `OPENAI_API_KEY` (or `GEMINI_API_KEY`) in `.env`, restart,
then in chat: “Kosmosdagi mushuk rasmini chiz” → “Fonini to'q ko'k qil” → open
**Yaratilganlar** (two versions). Without a key: “EZO arxitekturasi diagrammasini chiz”
still works, and “Instagram story tayyorla” shows a labelled placeholder.

## Phase 5 — Language Coach + IELTS-style simulator (2026-10-17) — alpha

*(Phase 1 after the 2026-10-18 renumbering.)*

**What changed**
- `LanguageCoachAgent`: real practice sessions with recorded learner and coach turns,
  computed metrics, a validated assessment, recurring-mistake tracking, goals, vocabulary and
  progress over time. EZO stays one assistant: an active session keeps ordinary English
  answers with the coach ("sticky" routing) until it is finished.
- Modes: free conversation, IELTS-style speaking (Part 1 → Part 2 task card → Part 3, with
  original questions), teacher, grammar, vocabulary, debate, job interview, travel, business
  English. CEFR adaptation from the request or the active goal.
- Assessment once per session on the `reasoning` route; practice turns on the cheap `chat`
  route. Model output is checked by rules: bands rounded and clamped, estimated range from the
  criteria mean (wider below 150 words), no band below 40 learner words, mistakes kept only if
  the learner really said the quoted text, unknown categories mapped to `other`.
- Exact computed metrics: words, moving-window lexical diversity, fillers per 100 words,
  repeated words, words per minute (only from measured voice time).
- Report artifact (DOCX with PDF and Markdown exports) in uz/en/ru.
- Web: “Til mashg'ulotlari” page (goal, trends, recurring mistakes, sessions, vocabulary,
  reports, delete with confirmation); voice turns send their measured speaking time.

**Files added:** `apps/api/src/ezo_api/db/models/language.py`,
`apps/api/migrations/versions/0004_language_coach.py`,
`apps/api/src/ezo_api/language/{analysis,modes,ielts,assessment,service,report}.py`,
`apps/api/src/ezo_api/agents/language_coach.py`, `apps/api/src/ezo_api/schemas/language.py`,
`apps/api/src/ezo_api/api/routes/language.py`, `apps/api/tests/unit/test_language.py`,
`apps/api/tests/integration/test_language_coach.py`,
`apps/web/components/language/LanguagePage.tsx` (+ test), `apps/web/app/language/page.tsx`,
`tests/e2e/specs/language.spec.ts`, `docs/LANGUAGE_COACH.md`.
**Files modified:** EzoCore (sticky routing, `speech_seconds`), intent rules, agent catalog,
`maturity.py`, chat schema and route, `main.py`, voice VAD/engine/speech, VoiceStage,
useChatSession, shared types and API client, history navigation, i18n (uz/en/ru), voice e2e
spec, README, ARCHITECTURE, TROUBLESHOOTING, ROADMAP.
**Database migrations:** `0004_language_coach` — `language_sessions`, `language_turns`,
`language_metrics`, `language_mistakes`, `language_goals`, `language_vocabulary`.

**Tests added:** 17 unit tests (metrics, mode/level/command/goal detection, IELTS flow, band
rounding and ranges, validation, localised honest report) and 5 integration tests (full
three-part simulator with assessment and report, free practice + finish + progress +
recurring mistakes, goals/API/privacy delete, too little speech, offline mode); one web unit
test; one Playwright spec; the voice e2e spec checks the measured speaking time.

**Security changes:** language data is per user (every query filtered by user); deleting a
session needs `?confirm=true` and removes its transcript, metrics and mistakes; raw audio is
never stored; the transcript is passed to the assessor as delimited data.

**User-visible changes:** say “IELTS speaking qilamiz” or “English speaking qilamiz” in chat
or voice; “Feedback ber” finishes a session; progress questions answer from stored results;
new “Til mashg'ulotlari” page.

**Known limitations:** English only; rule-based mode/command detection; the Part 2
preparation minute is not timed; pronunciation is transcript-assisted at best (acoustic
analysis is planned with realtime voice); bands are practice estimates, not calibrated
against real exam results. See `docs/LANGUAGE_COACH.md`.

**How the owner can test:** with an API key, open chat → “IELTS speaking qilamiz, B2
darajada” → answer the questions (typing or **Gaplashish**) → after Part 3 EZO gives
feedback and a report card → open **Til mashg'ulotlari**.

## Phase history (records made at the time)

Numbers in this history are the **local** results recorded when each phase finished. They
come from different environments and are not comparable with each other or with CI. Use
*Latest verified baseline* for current numbers.

### Baseline before Milestone 2 (2026-10-17, commit `b5d16c6`)

| Check | Result |
|---|---|
| Backend lint (`ruff check`) and format check | ✅ pass |
| Backend types (`mypy --strict`) | ✅ pass (61 files) |
| Backend tests on SQLite | ✅ 101 passed |
| Backend tests on PostgreSQL 16 | ✅ 101 passed |
| Frontend lint, type-check | ✅ pass |
| Frontend unit tests (Vitest) | ✅ 14 passed |
| Web production build | ✅ pass |
| Browser end-to-end tests (Playwright) | ✅ 9 passed |
| Docker images | ✅ built and stack ran (verified in the previous session; this cloud sandbox needs its proxy certificate added to temporary copies of the Dockerfiles) |

Milestone 1 features present and covered by tests: streaming chat, conversations, projects,
profile/project memory, EzoCore pipeline with intent routing and traces, provider abstraction
(Anthropic, OpenAI, Gemini, offline) with routing and fallback, personality engine,
browser voice conversation, uz/en/ru UI, auth (local/token), rate limiting, audit log.

Not yet implemented at baseline: Milestones 2–8 (see ROADMAP.md).

### Knowledge (Milestone 2) — verified 2026-10-17

| Check | Result |
|---|---|
| Backend lint + format (`ruff check` / `ruff format --check`, incl. scripts) | ✅ pass |
| Backend types (`mypy --strict`) | ✅ pass (101 files) |
| Backend tests on SQLite | ✅ 211 passed, 1 skipped (the pgvector-only test) |
| Backend tests on PostgreSQL 16 + pgvector | ✅ 212 passed |
| Migrations: fresh install, 0001 → 0002 upgrade with data, `alembic check`, downgrade | ✅ SQLite and PostgreSQL (with and without permission to create the `vector` extension) |
| Frontend lint + type-check | ✅ pass |
| Frontend unit tests (Vitest) | ✅ 38 passed (shared 9, web 29) |
| Web production build | ✅ pass (new route `/knowledge`) |
| Browser end-to-end tests (Playwright) | ✅ 15 passed (chat, voice, memory, projects, settings, mobile, presence states, files) |
| Docker | ✅ API and web images built; API container migrated a fresh PostgreSQL to 0002, used pgvector, ingested an upload into the `ezo-storage` volume as the non-root user, keyword search returned it; web container served `/` and `/knowledge` |

Docker note: this cloud sandbox reaches the internet through a proxy with its own certificate,
so verification builds used temporary copies of the Dockerfiles that add that certificate
(`--build-context ca=…`). The Dockerfiles in the repository are unchanged in that respect.

#### What works

Upload (paperclip or **Files** page) → validated, stored, read in the background → searchable
by keywords (always) and meaning (with an OpenAI/Gemini key) → EZO answers with numbered,
verified citations and lists the sources under the answer. Changed files become new revisions.
Web research via Claude web search or Tavily with official-source preference and dated citations.
Memories are retrieved semantically when embeddings are available. The orb shows real activity
(searching, reading…). Details: README “Files, knowledge and research”.

#### How to test

```bash
python scripts/ezo.py test --e2e                                   # everything
EZO_TEST_DATABASE_URL=postgresql://ezo:ezo@localhost:5432/ezo_test \
  uv run --project apps/api pytest apps/api/tests                  # backend on PostgreSQL
```

Manually: open **Files**, drop a PDF, wait for **Tayyor/Qisman**, then ask a question about it
in chat — the answer cites `[1]` and shows the source under it.

#### Configuration

`TAVILY_API_KEY`, `EZO_WEB_SEARCH_PROVIDER`, `EZO_WEB_SEARCH_MODEL`, `EZO_STORAGE_DIR`,
`EZO_MAX_UPLOAD_MB`, `EZO_VECTOR_STORE`, `EZO_INGESTION_MODE`, `EZO_FETCH_ALLOW_PRIVATE_NETWORKS`
(see `.env.example`); embedding models in `apps/api/config/models.toml` → `[[embeddings.candidates]]`.

#### Known limitations

No OCR (images/scans → “needs OCR”), no Qdrant or S3 implementations yet (interfaces exist),
ingestion runs inside the API process, some API messages are English-only, the reranker is a
pass-through. See ROADMAP “Known limitations”.

#### Security considerations

Content-sniffed uploads with size and zip-bomb limits; storage keys cannot escape the storage
folder; SSRF-safe fetching (private/loopback/link-local/CGNAT refused on every redirect,
robots.txt, size/type/time limits); source text treated as data (prompt-injection guard);
tool calls validated, time-limited, dangerous tools denied, every call audited with secrets
redacted; ownership checks on every document; uploads audited.

#### Quality gate

1. **Does it actually run?** Yes — API and web run locally and in Docker; upload → search → cited answer verified.
2. **Are tests passing?** Yes — numbers above, SQLite and PostgreSQL.
3. **Does Docker still work?** Yes — both images built and ran (see note on the sandbox certificate).
4. **Are migrations valid?** Yes — fresh install, upgrade from 0001 with data, `alembic check` clean, downgrade works.
5. **Does Milestone 1 still work?** Yes — all Milestone 1 tests and e2e specs still pass.
6. **Security regressions?** None found; new attack surfaces (uploads, URL fetching, tools) have dedicated protections and tests.
7. **Faked functionality?** No — OCR, Qdrant, S3 and model reranking are explicitly reported as not implemented; without embeddings or web search EZO says so.
8. **Understandable to a beginner?** Yes — one Files icon, a paperclip, status badges in Uzbek, and README/TROUBLESHOOTING sections in plain language.

### Voice / presence (open-source integration) — 2026-10-17

- ✅ Licence audit: [docs/OPEN_SOURCE_AUDIT.md](docs/OPEN_SOURCE_AUDIT.md), [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
- ✅ Phase 1 — EZO presence states (original code; unit, render and e2e tests).
- ✅ Phase 2 — voice providers (details below).

#### Voice providers — verified 2026-10-17

**What was changed:** new `voice/` package in the API (interfaces, OpenAI-compatible adapter,
fallback service), `/api/voice/status|transcribe|speak`, voice settings, an optional
`voicestudio` service in a `voice` Docker Compose profile, and a web voice engine (recording
with pause detection, server speech, automatic browser fallback). Settings → System status
shows the active voice.

**Code reused:** none. VoiceStudio (AGPL-3.0) is called over its documented OpenAI-compatible
HTTP API from a separate container; its source is not part of EZO. Everything else was written
from scratch.

**Tests:**

| Check | Result |
|---|---|
| Backend lint/format/mypy | ✅ pass (108 files) |
| Backend tests SQLite / PostgreSQL | ✅ 235 passed + 1 skipped / 236 passed |
| — voice unit tests | audio sniffing, adapter, error mapping, fallback order, `bad_audio` stop, configuration, **wire-format contract with the real OpenAI SDK** (paths, Bearer key, multipart, `language` field) |
| — voice API tests | no provider → 503 with hint; fallback with attempts; non-audio → 422; oversized → 413; speak MP3 + `no-store`; all failing → 502; audio never written to disk/DB; transcript → voice chat message |
| Frontend lint/typecheck/unit | ✅ pass; 43 unit tests (incl. pause detection) |
| Web production build | ✅ pass |
| Playwright | ✅ 17 passed, incl. server voice round trip with a synthetic microphone, tap-to-interrupt while EZO speaks, and server failure → browser listening and speaking |
| Docker | ✅ API image rebuilt and run: `/api/voice/status` lists VoiceStudio; with VoiceStudio unreachable, transcribe returns a clear 502 with the failed attempt. `docker compose config` valid with and without `--profile voice` |

**Known limitations:** the VoiceStudio container itself could not be started in this sandbox
(its registry is blocked by the sandbox proxy), so VoiceStudio was verified by the contract test
against its documented API, not live. Voice is turn-by-turn, not realtime streaming (the
`RealtimeVoiceProvider` interface exists without an implementation, Milestone 7). Pause
detection is a simple energy threshold (noisy rooms may end a turn late). VoiceStudio’s default
voice model is non-commercial.

**How the owner can test:** with `OPENAI_API_KEY` set, open **Gaplashish**, tap the robot, speak
a sentence and pause: EZO answers with OpenAI’s voice; tap while it speaks to interrupt. Without
keys the browser voice is used as before. For VoiceStudio see README → *Optional integrations*.

### Artifacts (Phase 3) — verified 2026-10-17

**What was changed:**
- Migration 0003 adds artifacts, immutable artifact versions and the story project tables.
- `ArtifactService`, `StoryService` and the timeline planner.
- `/api/artifacts`: list with filters, details, create from text or a message, rename, edit
  as a new version, restore, download, text preview and confirmed delete.
- `/api/stories`: CRUD, replacing scenes, reordering, timeline.
- Chat answers can be saved, and artifacts appear as cards under answers.
- New “Yaratilganlar / Created” page and history-panel icon, with uz/en/ru texts.
- CORS fix: the browser can now read download filenames, and PUT is allowed.

**Code reused:** none. Built on EZO’s existing StorageProvider and audit log.

| Check | Result |
|---|---|
| Backend lint/format/mypy | ✅ pass (118 files) |
| Backend tests SQLite / PostgreSQL | ✅ 252 passed + 1 skipped / 253 passed |
| — artifact tests | creation, download headers, edit → v2 with v1 preserved, identical content = no version, restore → v3 with parent, rename, filters, confirmed delete + storage cleanup, project deletion keeps artifacts, other users’ artifacts → 404 on every route, save answer from message (sources + message card), unsafe types/empty/unknown type rejected, path tricks sanitised, CORS exposure |
| — story tests | CRUD, ordering, invalid reorder, scene replacement, narration-aware timeline, assets limited to own artifacts, access control, project scope; timeline unit tests |
| Migrations | ✅ SQLite + PostgreSQL: fresh install, upgrade 0002 → 0003 (also on a database with existing data), `alembic check`, downgrade + re-upgrade |
| Frontend lint/typecheck/unit | ✅ pass; 46 unit tests |
| Web production build | ✅ pass (new route `/artifacts`) |
| Playwright | ✅ 18 passed, incl. save answer → card → Created → edit (v2) → restore (v3) → download → rename → delete |
| Docker | ✅ API image rebuilt; container migrated a fresh PostgreSQL to 0003; created an artifact, added v2, downloaded v1 unchanged; both versions stored in the volume |

**Quality gate:**
1. Runs? Yes, locally and in Docker.
2. Tests pass? Yes (numbers above).
3. Docker? Yes.
4. Migrations valid? Yes.
5. Chat, RAG and voice still work? Yes, all earlier tests and e2e pass.
6. Old versions preserved? Yes. Versions are never updated, restore appends, and tests check
   old content byte for byte.
7. Provenance? Yes. Each version records the parent version, creator, provider, model and
   sources. Saved answers keep their citations.
8. Failures reported honestly? Yes: missing file → 410, non-text edit → 409, unsupported type →
   422, other users → 404.
9. Security? Yes: owner scoping, sanitised names, content-addressed keys, server-decided MIME
   types, download headers, confirmed and audited deletes.
10. Beginner can test? Yes: press *Saqlash* under an answer, then open *Yaratilganlar*.

**Known limitations:**
- Only text artifacts can be edited in the UI. Binary files (PPTX, images) get new versions
  from the agents in later phases.
- Story projects have no UI of their own yet; they are used internally by Phase 4.
- Artifacts are stored locally. S3 storage is still interface-only.

### Documents + Presentations (Phase 4) — verified 2026-10-17

**What was changed:**
- `documents/`: format services (DOCX, PDF with bundled Liberation Sans, XLSX/CSV with a
  formula-injection guard, Markdown/TXT, spreadsheet analysis, diff, `OCRProvider` interface).
- `documents/render/`: own slide engine. 24 layouts, 5 themes, real font-metric text fitting,
  PPTX/PDF/HTML/PNG renderers from one layout plan, layout QA.
- Artifact **exports** per version (PDF, web, Word, Markdown, CSV, previews, deck spec), with
  a download endpoint and cleanup on delete.
- Tools: `read_document`, `create_document`, `create_spreadsheet`, `create_presentation`.
- `DocumentAgent` and `PresentationAgent` (catalog: available). Intent signals updated
  (presentation wins ties; translation/report/official-letter signals for documents).
- Web: “Other formats” downloads, slide thumbnails and QA result on the Created page.

**Code reused:** none copied. Libraries: python-pptx, reportlab, Pillow (new); python-docx,
openpyxl (existing). Liberation Sans fonts bundled under OFL 1.1 (see THIRD_PARTY_NOTICES).

| Check | Result |
|---|---|
| Backend lint/format/mypy | ✅ pass (151 files) |
| Backend tests SQLite / PostgreSQL | ✅ 310 passed + 1 skipped / 311 passed |
| — engine | every layout rendered; PPTX re-opened (python-pptx) and opened by LibreOffice; native charts with exact values; bullets via `buChar`; QA detects empty/overflow/duplicate/chart/table problems with slide numbers |
| — agents | file-based deck with sources slide and citations; reasoning route for the deck, chat route for the report; follow-up edit → v2 with story updated and v1 exports intact; QA repair round; invalid model output → nothing created, honest note; offline → nothing created; DOCX creation with placeholders; translation → derived artifact, original unchanged; follow-up rewrite → v2; comparison; spreadsheet facts; XLSX creation with empty unknowns and neutralised formulas; project scope; offline conversion |
| Frontend lint/typecheck/unit | ✅ pass; 46 unit tests |
| Web production build | ✅ pass |
| Playwright | ✅ 19 passed, new: attach file → “PDF ga aylantir” → PDF download → Word export download |
| Docker | ✅ API image rebuilt; inside the container: deck → PPTX + PDF + 2 previews, QA passed; DOCX/PDF/MD rendered; catalog lists document + presentation |
| Migrations | no schema change in this phase (exports live in version metadata) |

**Quality gate:**
1. Runs? Yes, locally and in Docker.
2. Tests pass? Yes (numbers above).
3. Docker? Yes.
4. Migrations valid? No new migration; 0003 unchanged and still verified by the suite.
5. Chat, RAG, research and voice still work? Yes, all earlier tests and e2e pass.
6. Old versions preserved? Yes. Edits and regenerations add versions, exports are per version,
   and tests read v1's spec after v2 exists.
7. Provenance? Yes: provider, model, `derived_from`, change summary, diff statistics, QA report
   and sources on every generated version.
8. Failures honest? Yes: no file → asks for upload; invalid model output, provider failure or
   offline → “nothing was created”; remaining QA issues are reported with slide numbers.
9. Security? Yes: owner + project scoping, source text wrapped as data in prompts, formula
   injection neutralised, server-decided MIME types, exports never rendered in the API origin.
10. Beginner can test? Yes: try the examples in README → *Documents and presentations*.

**Known limitations:**
- No image generation yet (abstract visuals on image slides); no OCR for scans.
- Conversion of uploaded PDFs/DOCX carries the text, not the original page layout.
- Long files: transformations process the first 40,000 characters and say so.
- Story projects still have no dedicated UI.

### Orchestration foundation + Ruflo audit — 2026-10-17

**What was changed:**
- `docs/OPEN_SOURCE_AUDIT.md` § 6 records the Ruflo audit: licence, security findings and
  decision.
- `docs/RUFLO_INTEGRATION_PLAN.md` covers architecture, security boundary, MCP strategy,
  allow-list, mission schema, lifecycle, approvals, fallback, UI, testing and deployment.
- `orchestration/`:
  - the `OrchestrationProvider` interface;
  - a working `NativeOrchestrationProvider`;
  - deterministic complexity routing and plan drafts;
  - the `AgentOutput` contract;
  - the security boundary: allow-list, deny-list, redaction, hardened environment.
- Settings: `EZO_ORCHESTRATION_PROVIDER`, `EZO_RUFLO_ENABLED`, `EZO_RUFLO_COMMAND`,
  `EZO_RUFLO_TIMEOUT_SECONDS`. Ruflo is off by default and falls back to native with a notice.

**Deliberately not done yet (per the roadmap):** missions are not started from chat. There are
no mission tables, no `RufloProvider` and no MCP client yet. Ruflo was not installed or
initialised anywhere, and no plugins or mods were enabled. No Ruflo code was copied.

| Check | Result |
|---|---|
| Backend lint/format/mypy | ✅ pass (158 files) |
| Unit tests (orchestration) | ✅ 25 tests: interface, routing on the spec examples, plan validation, lifecycle, parallelism, scoped inputs, retries, failure propagation, invalid output, timeouts, approve/reject, pause/resume, cancel, ownership, artifact linking, presence events, allow-list/deny-list, redaction, hardened environment, Ruflo fallback |
| Integration (realistic mission) | ✅ research → DOCX report via real tools → PPTX from both structured outputs → QA; mission completed, both artifacts linked and listed |

**Quality gate:**
1. Runs? Yes. Nothing user-visible changed, so chat is unchanged.
2. Tests pass? Yes (see the full suite numbers in the commit log).
3. Docker? Yes. No new dependency; the API image is unchanged.
4. Migrations? None needed yet; the mission tables are specified in the plan.
5. Existing features intact? Yes, all earlier tests pass.
6–7. Versions and provenance? Mission artifacts are ordinary versioned artifacts.
8. Honest failures? Yes. A mission fails when any step or the QA fails. Ruflo being
   unavailable falls back to native with a plain notice.
9. Security? Yes: allow-list plus hard deny-list, no secrets passed, isolated HOME, opt-outs
   for self-update, daemon and promo feeds, stdio only, and approval gates for actions with
   outside effects.
10. Beginner? Nothing to configure; see README → *Ruflo*.

## Next step

**Phase 3 — OCR + EZO Office**: a real `OCRProvider` (scanned PDFs, photos, screenshots, with
page numbers and confidence), PDF tools (merge, split, delete/reorder/rotate/extract pages,
image ↔ PDF, page numbers, watermark, compress), formatting-preserving DOCX edits and
chunk-aware long-document workflows. Then Phase 4 (education, academic research, career).
Ruflo stays off (Phase 14).
