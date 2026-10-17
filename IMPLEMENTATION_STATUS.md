# EZO implementation status

This file records what has been **verified** to work, milestone by milestone, and the exact
next step. Nothing is listed as working unless it was tested.

## Baseline before Milestone 2 (2026-10-17, commit `b5d16c6`)

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

## Milestone 2 — Knowledge, files and research (verified 2026-10-17)

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

### What works

Upload (paperclip or **Files** page) → validated, stored, read in the background → searchable
by keywords (always) and meaning (with an OpenAI/Gemini key) → EZO answers with numbered,
verified citations and lists the sources under the answer. Changed files become new revisions.
Web research via Claude web search or Tavily with official-source preference and dated citations.
Memories are retrieved semantically when embeddings are available. The orb shows real activity
(searching, reading…). Details: README “Files, knowledge and research”.

### How to test

```bash
python scripts/ezo.py test --e2e                                   # everything
EZO_TEST_DATABASE_URL=postgresql://ezo:ezo@localhost:5432/ezo_test \
  uv run --project apps/api pytest apps/api/tests                  # backend on PostgreSQL
```

Manually: open **Files**, drop a PDF, wait for **Tayyor/Qisman**, then ask a question about it
in chat — the answer cites `[1]` and shows the source under it.

### Configuration

`TAVILY_API_KEY`, `EZO_WEB_SEARCH_PROVIDER`, `EZO_WEB_SEARCH_MODEL`, `EZO_STORAGE_DIR`,
`EZO_MAX_UPLOAD_MB`, `EZO_VECTOR_STORE`, `EZO_INGESTION_MODE`, `EZO_FETCH_ALLOW_PRIVATE_NETWORKS`
(see `.env.example`); embedding models in `apps/api/config/models.toml` → `[[embeddings.candidates]]`.

### Known limitations

No OCR (images/scans → “needs OCR”), no Qdrant or S3 implementations yet (interfaces exist),
ingestion runs inside the API process, some API messages are English-only, the reranker is a
pass-through. See ROADMAP “Known limitations”.

### Security considerations

Content-sniffed uploads with size and zip-bomb limits; storage keys cannot escape the storage
folder; SSRF-safe fetching (private/loopback/link-local/CGNAT refused on every redirect,
robots.txt, size/type/time limits); source text treated as data (prompt-injection guard);
tool calls validated, time-limited, dangerous tools denied, every call audited with secrets
redacted; ownership checks on every document; uploads audited.

### Quality gate

1. **Does it actually run?** Yes — API and web run locally and in Docker; upload → search → cited answer verified.
2. **Are tests passing?** Yes — numbers above, SQLite and PostgreSQL.
3. **Does Docker still work?** Yes — both images built and ran (see note on the sandbox certificate).
4. **Are migrations valid?** Yes — fresh install, upgrade from 0001 with data, `alembic check` clean, downgrade works.
5. **Does Milestone 1 still work?** Yes — all Milestone 1 tests and e2e specs still pass.
6. **Security regressions?** None found; new attack surfaces (uploads, URL fetching, tools) have dedicated protections and tests.
7. **Faked functionality?** No — OCR, Qdrant, S3 and model reranking are explicitly reported as not implemented; without embeddings or web search EZO says so.
8. **Understandable to a beginner?** Yes — one Files icon, a paperclip, status badges in Uzbek, and README/TROUBLESHOOTING sections in plain language.

## Open-source integration (started 2026-10-17)

- ✅ Licence audit: [docs/OPEN_SOURCE_AUDIT.md](docs/OPEN_SOURCE_AUDIT.md), [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
- ✅ Phase 1 — EZO presence states (original code; unit, render and e2e tests).
- ✅ Phase 2 — voice providers (details below).

### Phase 2 — voice providers (verified 2026-10-17)

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

## Phase 3 — Artifact system + StoryProject foundation (verified 2026-10-17)

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

## Phase 4 — DocumentAgent + PresentationAgent (verified 2026-10-17)

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

## Next step

**Phase 5 — LanguageCoachAgent + IELTS-style speaking simulator** (estimated bands, never
“official” scores), then VisualAgent. Ruflo orchestration is audited and its architecture is
prepared (`docs/RUFLO_INTEGRATION_PLAN.md`); execution is scheduled after the foundations.
