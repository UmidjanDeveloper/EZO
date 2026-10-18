# Official knowledge sources (Phase 7 foundation) — experimental

EZO answers questions about Uzbekistan's legislation from **official texts it has retrieved
and versioned**. It never relies on model memory for them: laws change, so they live in the
knowledge base with their revisions, not in model weights.

## Status at a glance

| Part | State |
|---|---|
| `OfficialSourceConnector` framework, polite HTTP, sync, revisions, live verification | **Works** (tested with scripted websites on SQLite and PostgreSQL) |
| LegalResearchAgent (answers with official metadata, citations, currentness checks) | **Works, experimental** |
| LEX.UZ connector | **Built, off by default; live access NOT verified** (see below) |
| gov.uz, president.uz, E-qaror, ministry/education sites | **Not available** — no connector, access not reviewed |
| Automatic discovery of new acts | **Not available** — no verified feed or API; EZO re-checks the acts you track |

Mocked tests passing does **not** mean live LEX.UZ integration is complete. LEX.UZ could not
be reached from EZO's build environment (network policy), so the connector has never parsed
a real live page.

## What was verified about LEX.UZ (2026-10-18)

| Check | Result |
|---|---|
| Official API | None found. EZO uses the public document pages. |
| URL pattern | `https://lex.uz/docs/<id>` (Uzbek), `https://lex.uz/ru/docs/<id>` (Russian). Seen in public search results and third-party projects. |
| robots.txt | **Not verified** (host unreachable). EZO reads and obeys it at run time and does not fetch if it cannot read it. |
| Terms of use | **Not verified.** A third-party project states they do not restrict reuse; **the owner must check before enabling.** |
| Formats | HTML pages. Title format, e.g. `LRU-682-сон 20.04.2021. On normative legal acts`. |
| Rate limits | None published that could be found. EZO waits ≥ 5 s between requests and honours `Crawl-delay` and HTTP 429 `Retry-After`. |
| Legal basis (secondary sources; confirm with the official texts) | Copyright law LRU-42 art. 8: official documents are not objects of copyright. Law LRU-682 names the National Database of Legislation as an official source and lets electronic reference systems reproduce acts after official publication, with the source identified. |

## Enabling LEX.UZ (owner)

1. Open <https://lex.uz> and read its terms of use and `/robots.txt`. Continue only if
   automated retrieval of individual documents is permitted.
2. In `.env`: `EZO_OFFICIAL_SOURCES=lexuz`. Optional limits:
   `EZO_OFFICIAL_MIN_INTERVAL_SECONDS` (≥ 5 s is always applied),
   `EZO_OFFICIAL_MAX_DOCUMENTS_PER_RUN` (25), `EZO_OFFICIAL_MAX_RETRY_AFTER_SECONDS` (120).
3. Restart, then synchronize the acts you need by their LEX.UZ number (the digits in the
   page address):

   ```bash
   curl -X POST localhost:8000/api/official/sources/lexuz/sync \
     -H 'content-type: application/json' \
     -d '{"document_ids": ["5695915"], "language": "uz"}'
   ```

4. Check the result: `GET /api/official/runs`, `GET /api/official/documents`. Open one document
   (`GET /api/official/documents/{id}`) and **compare its title, number and text with the
   page on lex.uz**. That comparison is the first live verification of the connector; please
   report mismatches.
5. Ask in chat, e.g. “Normativ-huquqiy hujjatlar toʻgʻrisidagi qonunda rasmiy eʼlon qilish
   haqida nima deyilgan?”

## How it works

```
POST /api/official/sources/lexuz/sync
  → OfficialSyncService (one run, checkpoint after every document)
      → OfficialHttpClient: allow-listed host, robots.txt, ≥5 s pacing, request budget,
        401/403/451 = stop (never worked around), 429 = Retry-After (capped)
      → LexUzConnector.parse: title → number / type / authority / date; body → articles as
        sections; status only from an explicit label
      → compare content hash: unchanged | new | amended (new revision) | duplicate
      → KnowledgeService (existing): Markdown text → revision → chunks → embeddings / keyword
        index — so hybrid retrieval and citation checks are the normal ones
LegalResearchAgent
  → official_search (both Uzbek scripts; repealed/expired only for history questions)
  → verify_official_document (live re-check of the top acts when the source is enabled)
  → answer: title, number, date, status, article, retrieval date, official URL, [n] citations
```

### Stored for every act (`legal_documents`)

Stable source ID, title, number, issuing authority, type, language and script, adoption /
publication / effective dates (only when stated), status with **where it came from** and
**when it was verified**, official URL, content hash, current revision, last successful
retrieval, last check (and its error), duplicate link, provenance (fetched URL, content type,
time, warnings). Every retrieved version is a `legal_revisions` row, linked to its knowledge
revision and to the raw page exactly as received. Nothing is overwritten or deleted by a sync.

### Honesty rules (in code and tests)

- **No invented facts.** Number, type, authority and dates come only from the page title.
  Anything not stated stays empty and is shown as "not stated".
- **Status.** It is read only from an explicit status label, never from body wording, because
  laws often declare *other* acts repealed. Without a label the status is
  `unknown`, and EZO says it could not be confirmed and never calls the act "in force".
- **Live check failed.** EZO shows the last verified retrieval time and does not claim
  currentness.
- **Revision comparison.** EZO compares the texts *it retrieved*. Their dates are retrieval
  dates, not official amendment dates, and EZO says so.
- **Unverified sources** cannot be enabled. Their endpoints are not invented.

## Security

- Only `https://lex.uz` / `https://www.lex.uz` can be contacted through the connector, via the
  SSRF-protected fetcher (public IPs only, size and type limits, redirects re-checked).
- Document IDs are digits only. Nothing user-supplied is ever pasted into a URL path
  unchecked.
- Sync is owner-triggered, rate-limited (`chat` limit) and audited (`official.sync`,
  `official.resume`, `official.verify`).
- Official texts reach the model as delimited source data, like every other source.

## Known limitations

- No live verification of the connector yet (see above).
- No change feed: new acts must be named by ID; amendments are detected when tracked acts are
  re-synchronized or checked live. There is no scheduler yet (durable jobs are Phase 5).
- Official texts belong to the user who synchronized them (single-owner EZO). A shared corpus
  comes with multi-user accounts.
- Publication and effective dates are not extracted yet (they are not in the title).
- Uzbek Latin ↔ Cyrillic search uses a rule-based transliteration of the query.
