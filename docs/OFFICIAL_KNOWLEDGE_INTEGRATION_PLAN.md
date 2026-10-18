# Official knowledge × EZO Office — integration plan (preparation only)

**Status: plan. Nothing in this document is activated.** No new source was connected, no
site was contacted, and no feature flag was changed for it. The existing official-source
framework (connector, LEX.UZ proof of concept, sync, LegalResearchAgent) is described in
[OFFICIAL_SOURCES.md](OFFICIAL_SOURCES.md). LEX.UZ stays **off by default**
(`EZO_OFFICIAL_SOURCES` empty) and its live access is **not verified**: the build
environment cannot reach lex.uz, gov.uz, president.uz or e-qaror.

## 1. Goal

Let EZO Office (PDF, OCR, Word, Excel, long documents) work with official legal texts
in a way that is verifiable:

| User need | Example | What EZO would do |
| --- | --- | --- |
| Check references in a document | "Bu shartnomadagi qonun havolalarini tekshir" | Find references such as "LRU-682", "5-modda" or "ПП-1234 от 12.03.2021" in the uploaded file (OCR'd if needed), look each one up among **synced** official texts, and report found / not synced / repealed / amended, with the revision date |
| Quote the current wording | "Mehnat kodeksining 131-moddasini hujjatga qo'sh" | Insert the article text from the synced official revision, with source URL, act number, date and "verified on" timestamp |
| Compare with an old version | "Bu hujjatdagi modda matni hozirgisi bilan bir xilmi?" | Compare the quoted text with the current official revision (the existing compare engine), and show the differences |
| Long official acts | Summarise a 300-page code | Use the long-document pipeline (Step 5) on the synced text, citing articles |
| Official letters | "Rasmiy xat tayyorla" | The existing templates, plus optional links to the legal basis the user picks |

## 2. Principles (from the owner's rules)

- Never fabricate an act, number, date, article or endpoint. An unsynced reference is
  reported as **"not in EZO's official library"**, never guessed from model memory.
- Never bypass access controls. Use only sources whose terms and robots.txt the owner
  has reviewed (AccessReview in code). Pace requests (≥ 5 s), honour Retry-After, stop
  on 401/403/451.
- Sources are configuration. Each one is enabled explicitly by the owner.
- Mocked tests are not proof of a live integration. A source counts as integrated only
  after a successful, logged live sync that the owner has checked.
- **LegalResearchAgent is not activated further by this plan.** See §6 for the current
  state, which conflicts with the Phase 3 instruction, and what the owner must decide.

## 3. Building blocks that already exist

| Block | Where | State |
| --- | --- | --- |
| Connector framework, polite HTTP client, AccessReview | `official/base.py`, `official/http.py`, `official/registry.py` | works in mocked tests |
| LEX.UZ connector | `official/lexuz.py` | built, off, live access not verified |
| Versioned legal documents + revisions, sync runs | `legal_documents`, `legal_revisions`, `official_sync_runs` (migration 0005) | works in mocked tests |
| `official_search`, `verify_official_document` tools | `tools/official_tools.py` | works with synced data |
| Reference-free document engines | PDF engine, OCR, DOCX in-place editing, tables, long documents | Phase 3 Steps 1–5 |

## 4. Proposed work (after owner approval)

1. **Reference extractor** (`documents/legal_refs.py`): deterministic patterns for Uzbek
   Latin and Cyrillic, Russian and English. Covers law numbers (`LRU-682`, `ЗРУ-682`),
   decrees (`PF-`, `ПФ-`), resolutions (`PQ-`, `ПП-`, `VMQ`), dates and articles
   (`5-modda`, `статья 5`). Results are shown as "candidates", never as facts.
2. **Reference check tool** (`check_legal_references`): for each candidate, look it up
   in the synced library only and return found / not synced / repealed /
   amended-since(date). No web call unless the owner enabled a source **and** the user
   asked for a live check (`verify_official_document`).
3. **Insert official wording into Word** with the Step 3 in-place editor: the inserted
   paragraph carries a footnote-style source line (act, article, revision date, URL,
   verified-at). As tracked changes on request.
4. **Comparison report** of a quoted article against the current revision, with the
   existing compare engine. Output as DOCX/PDF with both texts and the differences.
5. **UI**: a "Legal references" panel on document artifacts. Each reference shows a
   status chip; "not synced" offers "add to tracked acts" (owner only, when a source is
   enabled).
6. **Tests**: reference extraction across the three languages and both scripts. Library
   lookups use fixtures only. A test proves that nothing is looked up on the web when
   sources are off.

Estimated size: about one Phase 3 step. No database migration is needed for 1–2; 5 may
need a small table for per-artifact reference results.

## 5. What must be true before any of this goes live

| Condition | Who | Status |
| --- | --- | --- |
| LEX.UZ terms of use and robots.txt reviewed and recorded | owner | **open** |
| A live sync of a few known acts succeeded and was checked by a person | owner + EZO | **open** (network blocked in the build environment) |
| gov.uz / president.uz / e-qaror: official API or permitted access identified | owner | **open**; no connector exists |
| Decision on LegalResearchAgent visibility (§6) | owner | **open** |
| Licence for the EZO repository | owner | **open** (no licence chosen) |

## 6. LegalResearchAgent — current state and the decision needed

The previous task ("Official Knowledge Integration") built LegalResearchAgent and
registered it as **experimental and available**. With no source enabled it does
nothing harmful: it answers that no official texts are synced and cites nothing. The
Phase 3 instruction says *"Do not activate LegalResearchAgent merely because the plan
exists"*. This plan activates nothing. The agent's state is unchanged, but it is
already visible.

Options for the owner:

1. **Keep as is** (visible, experimental; honest "no texts synced" answers).
2. **Hide until a source is live.** A small change: mark it unavailable while
   `EZO_OFFICIAL_SOURCES` is empty, so legal questions go to the general agent with a
   "not legal advice" note.

EZO recommends option 2 until a live LEX.UZ sync has been verified, but makes no change
without the owner's decision.

## 7. Out of scope

Scraping restricted sites, logging into government portals, paid databases, legal
advice or "official interpretation", and any claim of being an official legal service.
