# Knowledge OS and SkillForge

Status: **K1 — source registry and secure reading: experimental.** K2–K7 are not built.
SkillForge (turning knowledge into tools) does not exist yet: **EZO cannot create,
install or run skills.** Reading a source only adds searchable knowledge.

| Phase | What | State |
| --- | --- | --- |
| K1 | Libraries, learned sources, secure reading of websites / GitHub / PyPI / npm | experimental (this page) |
| K2 | Library-scoped retrieval in chat, citations, versions, stale-source warnings | not built |
| K3 | Capability analysis, comparison with existing EZO tools, skill proposals | not built |
| K4 | Secure sandbox (isolated container, no secrets, no network by default) | not built — required before any generated code runs |
| K5 | Skill builder and verification | not built |
| K6 | Skill registry, approval, restricted runtime, rollback | not built |
| K7 | Change detection and owner-approved upgrades | not built |

## K1 — what works

Knowledge page → **Bilim kutubxonalari**, or in chat.

| Try | Result |
| --- | --- |
| "Ezo, shu website'ni o'rgan: https://docs.example.org/guide/" | The site is read inside that folder and indexed |
| "Mana bu GitHub repository'ni o'rgan: https://github.com/owner/repo" (or `github:owner/repo`) | Metadata, licence, commit, file map; README, licence, manifests, docs, API specs, examples and entry points read **as text** |
| "pypi:requests ni o'rgan" / "pip install httpx ni o'rgan" | Registry facts (version, licence, dependencies, links), README and the linked documentation site |
| "npm:react ni o'rgan" | Registry facts, entry points, README, homepage documentation |
| "Buni «Python kutubxonalari» kutubxonasiga o'rgan: …" | Into a named library (created when missing) |
| "O'rgangan manbalaringni ko'rsat" | Every library and source with its status, version, licence and problems |

After reading, the documents are part of your knowledge base: EZO's normal file search
(keyword, and semantic when an embedding key is set) finds them, with citations to the
page or file. They persist across restarts. Deleting a source removes its documents,
chunks, vectors and stored files.

### Status (always from the database, never guessed)

`queued` → `inspecting` (Manba tekshirilmoqda) → `reading` (Dokumentatsiya o'qilmoqda) →
`indexing` (Bilimlar indekslanmoqda) → `indexed` (O'rganildi) / `partial` (Qisman) /
`failed`. **Partial** means something was not read: a budget limit, a page or file error,
an unreachable documentation site, or the GitHub fallback. The reason is shown.

### Reading rules

- **Websites**: only the start page's host and folder
  (`https://docs.x.org/en/latest/…` never goes to `/en/` or another host); robots.txt for
  every page and its Crawl-delay; one request at a time per host with at least 1 s
  between requests; links to archives, images, executables, scripts and office files are
  never requested.
- **GitHub**: REST API (`EZO_GITHUB_TOKEN` optional: without it 60 requests/hour; with it
  also your private repositories; the token is sent only to api.github.com and never
  follows a redirect). Files are read from `raw.githubusercontent.com` at the exact commit.
  If the API is refused, well-known files are read from the default branch and the source
  is marked **partial** (commit unknown). Nothing is cloned or installed; `node_modules`,
  vendored code, binaries and shell scripts are skipped.
- **PyPI / npm**: public registry JSON; README; the documentation site linked by the
  package, within the same budget. No wheels, tarballs or install scripts.
- **Budgets** (per run, adjustable within hard caps): pages/files 25 (≤200), depth 2
  (≤4), total 20 MB (≤100), file 512 KB (≤5 MB), time 300 s (≤30 min).

### Safety

- Every request goes through EZO's SafeFetcher: http/https only, no credentials in
  URLs, every hostname and redirect hop must resolve to public addresses, and — new in
  K1 — the address actually connected to is checked again (DNS rebinding) when the
  connection is direct. Size, type and time limits apply.
- **External text is data.** Passages that try to instruct an AI ("ignore previous
  instructions", "reveal your API keys", `curl … | sh`, also in Uzbek and Russian) are
  recorded on the source, shown in the UI and audit-logged
  (`learning.injection_suspected`); nothing is executed because of them. Answers keep the
  rule that `<source>` text is not instructions.
- **Licences**: recognised permissive licences (MIT, Apache-2.0, BSD, ISC…) are marked
  fine with notices; copyleft or restricted ones (GPL, AGPL, LGPL, MPL, SSPL, BUSL,
  CC-BY-SA/NC…), unknown and missing licences are marked **needs review** before any code
  is reused in a commercial product. This is not legal advice.
- Every add, read, refresh and delete is audit-logged.

### API

| Method | Path | Notes |
| --- | --- | --- |
| GET / POST | `/api/learning/libraries` | list (with source counts) / create `{name, description}` (409 for a duplicate name) |
| DELETE | `/api/learning/libraries/{id}` | removes its sources and their documents (409 while one is being read) |
| GET | `/api/learning/sources?library_id=` | sources with status, version, licence, stats, flags |
| POST | `/api/learning/sources` | `{target, kind?, library_id? \| library_name?, limits?}` → 202 and reading starts; an existing source in that library → 200 with `created: false`; private addresses → 422 `blocked` |
| GET | `/api/learning/sources/{id}` | plus the documents read |
| POST | `/api/learning/sources/{id}/refresh` | read again (unchanged documents are not re-indexed; `stats.content_changed`) |
| DELETE | `/api/learning/sources/{id}` | source, documents, chunks, vectors, stored files |

`GET /api/knowledge/documents` leaves learned pages out unless `include_learned=true`.

### Configuration

- `EZO_GITHUB_TOKEN` — optional, read-only fine-grained token.
- `EZO_LEARNING_ENABLED=false` — turns learning off (existing sources can still be
  deleted).
- Reading runs in the background (`EZO_INGESTION_MODE=background`); interrupted sources
  are read again at startup.
- No AI key is needed to read and keyword-index sources; semantic search needs an
  embedding key (OpenAI or Gemini).

## Limits (honest)

- Chat answers use learned sources through the general file search; there is no
  "answer only from this library" yet (K2).
- No scheduled re-checks or change notifications; "refresh" is manual (K7).
- JavaScript-rendered documentation sites are read as served HTML only.
- GitHub without a token allows about 60 API requests per hour.
- Live access verified from the development sandbox: **PyPI, the npm registry and
  raw.githubusercontent.com** (e.g. `pypi:httpx` 0.28.1 BSD-3-Clause, `npm:left-pad`,
  `github:psf/requests` via the raw fallback). **Not verified live**: the GitHub REST API
  (403 from the sandbox network) and general documentation websites (DNS blocked there).
  Those paths are tested with recorded responses and, for websites, a real local site in
  the Playwright suite.
