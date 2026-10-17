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
- ✅ Phase 1 — EZO presence states (original code; verified by unit, render and e2e tests above).

## Next step

**Phase 2 — voice providers.** Add `SpeechToTextProvider` / `TextToSpeechProvider` interfaces
in the API, an OpenAI voice provider and an optional `VoiceStudioProvider` (its
OpenAI-compatible `/v1/audio/*` HTTP API, separate container in a `voice` Docker profile),
`/api/voice/*` endpoints with size limits and no stored audio, and keep the browser voice as
the fallback. Then Milestone 3 (Language Coach) builds on that voice layer.
