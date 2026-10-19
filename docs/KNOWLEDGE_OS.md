# Knowledge OS and SkillForge

Status: **K1, K2 & K3 completed — source registry, secure reading, library-scoped retrieval, chat integration, and capability analyzer.**
K4–K7 are not built.
SkillForge (turning knowledge into tools) does not exist yet: **EZO cannot create,
install or run skills.** Reading a source only adds searchable knowledge; capability analysis
produces strictly read-only, non-executable proposals.

| Phase | What | State |
| --- | --- | --- |
| K1 | Libraries, learned sources, secure reading of websites / GitHub / PyPI / npm | done |
| K2 | Library-scoped retrieval in chat, citations, versions, stale-source warnings | done (2026-10-19) |
| K3 | Capability analysis, comparison with existing EZO tools, skill proposals | done (2026-10-19) |
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
| GET | `/api/learning/libraries/{id}` | get library details with source counts |
| GET | `/api/learning/sources?library_id=` | sources with status, version, licence, stats, flags |
| POST | `/api/learning/sources` | `{target, kind?, library_id? \| library_name?, limits?}` → 202 and reading starts; an existing source in that library → 200 with `created: false`; private addresses → 422 `blocked` |
| GET | `/api/learning/sources/{id}` | plus the documents read |
| POST | `/api/learning/sources/{id}/refresh` | read again (unchanged documents are not re-indexed; `stats.content_changed`) |
| DELETE | `/api/learning/sources/{id}` | source, documents, chunks, vectors, stored files |

`GET /api/knowledge/documents` leaves learned pages out unless `include_learned=true`, and accepts `library_id` to scope listing.
`POST /api/knowledge/search` accepts `library_id` to strictly scope search to documents in that library.

## K2 — Library-Scoped Retrieval & Chat Integration (what works)

- **Chat Library Selection**: In Chat UI, select any saved library from the library dropdown.
- **Strict Library Scoping**: When a library is selected, all retrieval (`Retriever.retrieve()`, keyword search, vector filter) resolves strictly to that library's authorized document IDs.
- **Ownership & Isolation**: Another user's library answers 404, exactly like a library that does not exist, so its existence is not revealed. Library A never leaks into Library B. The scope also applies to presentations built from your files.
- **No Silently Falling Back**: If a library has no relevant documents or is empty, EZO explicitly states that no relevant information was found in that library. It never silently falls back to global search.
- **Source Provenance & Freshness Badges**: Citations display title, external URL, version (package version, or the exact commit for GitHub; the latest release stays in the profile), license (e.g. `MIT`), and last checked timestamp. Freshness is decided age first:
  - `not_recently_checked` (30 kundan ortiq tekshirilmagan): not re-checked in the last 30 days — whatever happened before.
  - `changed` (Manba yangilangan): the last re-check found new content; the cited text *is* the updated text.
  - `current`: checked within 30 days and unchanged.
- **Prompt boundary**: cited text is data. Any `<source` / `</source` inside it is escaped so it cannot close the quoted block, and titles are quoted, not trusted.
- **Library deletion**: deleting a library clears it from its conversations and posts a short notice there that EZO now uses all your files again.
- **Strict instruction scope**: the "answer only from this library" rule is given to the agents that answer from documents (`general`, `research`, `knowledge_os`); other agents get a soft note.
- **Turn Continuity & Switching**: Library scope persists across chat turns in the conversation. Users can switch libraries or clear the scope (`clear_library: true`) to return to normal global retrieval.
- **Knowledge Page Search**: Filter and search within a specific library directly on the Knowledge page.
- **Multi-lingual**: Fully localized in Uzbek, Russian, and English.

### When chat starts learning

A message is routed to the learning agent only when it is an explicit instruction to learn
or read ("o'rgan", "o'qib chiq", "bilim bazasiga qo'sh", "learn/study/index this", "изучи",
"прочитай и запомни"…) **and** names a source (URL, `github:`, `pypi:`, `npm:`, a library).
Messages with attachments, presentation, visual and language-coach requests keep their own
agent, and a forced agent always wins. "Tahlil qil / analyze" only analyses a repository or
package that is named.

## K3 — Capability Analyzer (what works)

K3 enables EZO to inspect previously learned libraries and sources to formulate grounded capability proposals:

- **10-Point Structured Analysis**:
  1. Source identity and version (e.g. `pypi:pypdf`, version `6.21.1`).
  2. Main purpose and domain summary.
  3. Described capabilities and technical modular features.
  4. Active EZO registry equivalents: matched by whole words against the tools and agents actually registered at runtime (e.g. `pdf_tool`, `ocr_tool`); an unregistered agent counts as missing.
  5. Missing functionality specific to EZO's current toolset.
  6. Domain relevance and mission alignment rationale (`high`, `medium`, `low`, `irrelevant`).
  7. Third-party dependencies and required security permissions (`file_read`, `isolated_sandbox`, `network_outbound`).
  8. License review and compatibility risk assessment (`safe`, `copyleft`, `review_needed`, `unknown`); GPL/AGPL/LGPL/MPL… map to `copyleft`.
  9. Future implementation roadmap and next development steps (e.g. for K4 Sandbox).
  10. Multi-level evidence grading (`directly_supported`, `inferred`, `unverified`) and completeness assessment. Keyword matches are never "directly supported": every proposal derived from them is `inferred` (confidence ≤ 0.6) and lists its evidence gaps.

- **Strict Read-Only Guarantee**:
  - All proposals are assigned `status: "proposal"`.
  - External documentation text is treated strictly as passive untrusted data.
  - Prompt-injection attempts (`override`, `exfiltration`, `system_prompt`) are neutralized, logged as passive data, and recorded under `security_warnings`.
  - EZO **never** executes code, installs packages, runs shell commands, creates executable skills, or edits runtime files.

- **Bounded and cached**: at most 50 documents and 20,000 characters per document are read; a result is reused while the source's content hash and the analyzer version are unchanged. Analysis of a source that is still being read answers 409.
- **Report boundary**: in chat, the analysis report reaches the model as a quoted `<source>` (data), never as system notes.

- **Deduplication Engine**:
  - Multiple sources in a library describing overlapping capabilities are unified into merged proposals with combined evidence and dependency unions.

- **API Endpoints**:
  | Method | Path | Description |
  | --- | --- | --- |
  | `POST` | `/api/learning/libraries/{id}/analyze` | Analyzes all sources in a library, aggregates proposals, and deduplicates. |
  | `GET` | `/api/learning/libraries/{id}/capabilities` | Retrieves existing capability analysis report for a library. |
  | `POST` | `/api/learning/sources/{id}/analyze` | Runs deep capability analysis on a specific learned source. |
  | `GET` | `/api/learning/sources/{id}/capabilities` | Retrieves stored capability analysis profile for a source. |

- **Chat Integration**:
  - Natural language queries like *"EZO, analyze the documentation you learned from this Python library. What useful abilities could you gain?"* trigger capability analysis.
  - Formats structured reports with full evidence citations and explicit read-only disclaimers.

- **Web UI Integration**:
  - **Imkoniyatlarni tahlil qilish** button on each library card in the Knowledge page.
  - Interactive proposal drawer with capability badges, relevance scores, evidence excerpts, and license risks.
  - Explicit warning badges confirming that proposals are non-executable and not installed.

### Configuration

- `EZO_GITHUB_TOKEN` — optional, read-only fine-grained token.
- `EZO_LEARNING_ENABLED=false` — turns learning off (existing sources can still be
  deleted).
- Reading runs in the background (`EZO_INGESTION_MODE=background`); interrupted sources
  are read again at startup.
- No AI key is needed to read and keyword-index sources; semantic search needs an
  embedding key (OpenAI or Gemini).

## Limits (honest)

- Re-checking is manual via the "refresh" action (`/refresh`); automated scheduled re-checks are planned for K7.
- JavaScript-rendered documentation sites are read as served HTML only.
- GitHub without a token allows about 60 API requests per hour.
- Live access verified from the development sandbox: **PyPI, the npm registry and
  raw.githubusercontent.com** (e.g. `pypi:httpx` 0.28.1 BSD-3-Clause, `npm:left-pad`,
  `github:psf/requests` via the raw fallback). **Not verified live**: the GitHub REST API
  (403 from the sandbox network) and general documentation websites (DNS blocked there).
  Those paths are tested with recorded responses and, for websites, a real local site in
  the Playwright suite.
