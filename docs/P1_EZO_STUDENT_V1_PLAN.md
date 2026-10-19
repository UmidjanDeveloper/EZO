# P1 — EZO Student V1 implementation plan

Status: plan only, based on integration c09e94ce9dc29b2e2a9ec467bbaee3c4d902d9b1
and the current P0 audit. No Student milestone, new infrastructure, live provider
usage or K4–K7 implementation is authorized by this document alone.

EZO Student should help an authorized learner understand their own sources in Uzbek
first, with English and Russian support, traceable explanations and realistic progress.
Production or hostile multi-user readiness must not be inferred from the existing
single-owner alpha/experimental capabilities.

## What already exists, checked in code

| Need | Reusable implementation | Gap |
| --- | --- | --- |
| PDF/DOCX ingestion | knowledge/uploads.py, parsers/pdf.py and office.py; bounded archive checks, revisions, OCR | EPUB absent; parsers run in API threads; no isolated durable worker |
| Sections/pages | parsers/base.py Section(text, page, heading); longdoc.py heading-aware parts | no immutable, addressable reading manifest or full chapter hierarchy |
| Retrieval/citations | ingestion/chunking.py; retrieval/sources.py and citations.py; PostgreSQL/local vector stores; K2 libraries | location metadata is not a complete reading structure; semantic quality needs a separately approved live evaluation |
| Source permissions/provenance | learning targets/readers/safety; source revisions, license/security flags, robots/SSRF/budgets | legal permission cannot be inferred from robots.txt or a successful HTTP response |
| Learning outputs | education materials/quizzes; language-coach goals, mistakes and vocabulary | no source-grounded Student flashcard/study-set domain or progress history |
| Identity | owner-scoped User and Project filters, token auth | no workspace membership, multi-user identity or tenant administration |
| Jobs | API-local ingestion/learning with restart resume | no leases, fencing, durable cancellation, isolated parser executor or independently supervised worker |
| Phone UI | existing Knowledge page, source cards and uz/en/ru strings | no dedicated Student reader/practice/progress journey |

K3 remains deterministic, confidence-labelled and proposal-only. It is not the Student
execution engine. Reading source text never grants installation, secret access, source
modification, git push or deployment authority.

## Review-sized milestone order

| Milestone | Deliverable | Dependency / boundary |
| --- | --- | --- |
| P1.1 | Versioned DOCX reading manifest and read-only owned-section API | existing supported format; one small backend PR, detailed below |
| P1.2 | Durable ingestion jobs and separately constrained parser process | before large books, unattended work or hostile multi-user input; local tests only |
| P1.3 | PDF page manifests, EPUB spine/navigation, permitted web sections | isolated P1.2 parser; each format in a separate PR; no DRM/paywall bypass |
| P1.4 | Structured scoped retrieval and cross-source explanation evaluation | stable section IDs/revisions; grounded uz/en/ru fixtures; no invented citations |
| P1.5 | Source-grounded study guide, quiz and flashcard sets | reuse education/language services; generation and answer grading remain distinct |
| P1.6 | Mobile reader/practice/progress journey | versioned study sets, accessible interactions, explicit workspace/identity scope |
| P1.7 | Student V1 readiness gate | worker recovery, resource budgets, tenant negatives, quality evaluation and independent security review |

Each row can have smaller PRs. P1.3–P1.6 are not bundled into P1.1. Multi-user rollout
requires a separately reviewed authentication/workspace membership boundary before
accepting a second owner's data; Project is not silently redefined as a secure tenant.

## First milestone: P1.1 — immutable DOCX section reading

### User-visible/API contract

An authenticated owner can inspect sections of an already indexed, authorized DOCX.
Keep registration/upload/reindex flows unchanged. No new formats, embeddings, AI calls,
external requests, jobs, quiz generation or UI redesign in this first PR.

Proposed endpoints under the existing authenticated knowledge router:

- GET /api/knowledge/documents/{document_id}/reading-manifest?revision_id=...&offset=0&limit=50
- GET /api/knowledge/documents/{document_id}/reading-sections/{section_id}?revision_id=...&offset=0&limit=4000

The API returns server-sliced text; it does not send an entire book to render one section.
Maximum manifest page 100 entries; maximum section-text page 8,000 Unicode code points.
Current revision is the default. Validate explicit revision-to-document-to-owner and
project relationships before returning anything. Unknown/other-owner IDs return 404.
Do not allow the caller to provide a filesystem key.

Manifest v1 contains: document_id, revision_id, revision_number, content_hash,
parser_version, manifest_version, offset_unit=unicode_codepoints, total_sections,
reading_order and bounded section entries:
section_id, ordinal, heading (max 200 chars), heading_level=null when unknown,
start_offset, end_offset, locator_kind=section, page=null for DOCX.

Store offsets into the exact canonical DocumentRevision.raw_text, not into separately
normalized or model-generated text. Build canonical text and offsets together so every
section equals raw_text[start_offset:end_offset], including Uzbek apostrophes,
Cyrillic and emoji. Do not claim DOCX page numbers: pagination needs a layout engine.

Section IDs must be deterministic within an immutable revision and parser version,
and distinguish repeated/empty headings by ordinal. New revision => different IDs.
Use paragraph/style structure already produced by the DOCX parser. Do not infer a
chapter hierarchy from appearance or use an LLM to invent chapter numbers. Heading
level can be added to Section later if verified from the actual Word style.

For a heading-free document use an honest continuous-text section, served in bounded
text pages. For this initial contract refuse more than 2,000,000 extracted characters
or 500 structural sections with an explicit resource-limit response; do not truncate
silently. This is a bounded first milestone, not large-book support.

Existing revisions without a manifest return 409 reading_structure_unavailable plus
an explicit reindex-required indication. GET must not parse a file, call a provider or
mutate the revision. Reindex must follow the existing explicit owner action and
provider-cost policy. Do not manufacture locators from legacy mixed-location chunks.

### Files/components and ordered implementation tasks

1. Add knowledge/reading.py: versioned manifest dataclasses/Pydantic contract, canonical
   section serialization, deterministic IDs, offset construction and size validation.
2. Extend knowledge/parsers/office.py and parsers/base.py only as needed to retain
   verified DOCX section structure; preserve current extraction text and table ordering.
3. Update knowledge/ingestion/service.py to persist a bounded reading_manifest_v1 in
   DocumentRevision.meta in the same transaction as that revision's successful parse.
   Raw text is stored once; manifest carries offsets, not a second complete text copy.
4. Add schemas/reading.py and the two read-only routes in api/routes/knowledge.py.
   Reuse current owner/project authorization; add explicit revision ownership joins.
   No new SQL table/migration is expected for the bounded JSON manifest. If actual
   implementation requires a new table, stop that assumption and review a migration
   separately rather than hiding schema work in the parser PR.
5. Add tests/unit/test_reading_manifest.py and
   tests/integration/test_reading_api.py. Update generated/shared API types only if
   this repository's actual contract consumers need them.
6. Update a short Student reading contract document and the existing maturity/status
   records. Keep Student experimental. No frontend implementation is required yet.

Paths above are relative to apps/api/src/ezo_api except explicitly named tests.
No new dependency is expected; use existing DOCX/XML, Pydantic and SQLAlchemy packages.

### Acceptance criteria and meaningful tests

- Deterministic manifest for the same immutable revision; duplicate headings have
  distinct IDs; revision changes cannot reuse a stale section identity.
- Every offset is in range and slices the exact canonical text. Cover uz/en/ru,
  Cyrillic, apostrophes, emoji, blank paragraphs, tables and heading-free files.
- API page limits are enforced; huge/malformed structures fail explicitly with no
  silent text loss or full-book response allocation.
- Every cross-owner/document/revision/project combination is denied with 404;
  deleting a source/document removes or makes its sections inaccessible.
- GET is read-only and offline: deny process creation/provider/network/storage reads
  in the route test and verify manifest requests still succeed from persisted data.
- Source instructions such as install this tool or reveal a key remain returned text;
  no tool registry, repository file or permission state changes.
- Existing DOCX extraction, K1–K3, chat, IELTS and presentation suites remain green.
- Run SQLite and real PostgreSQL tests; no parser assertion or citation test is weakened.
  A fake provider is used in CI. Live model quality is not claimed.

## P1.2 — durable jobs and parser containment

Any parser isolation needed to close the P0 security gate must be completed as a
separate P0 hardening change first. P1.2 extends/reuses that boundary for durable
Student jobs; it is not permission to postpone a P0 blocker until a product feature.

Use PostgreSQL as the first durable job store/lease queue to reuse the existing
database and avoid requiring Redis infrastructure for the Student first iteration.
Record this as the Phase 5 queue ADR before coding. Redis remains a future option
when measured scale justifies a new service/dependency, not a prerequisite now.

Proposed components: services/worker, jobs service/models, one additive Alembic
migration, queue claim/heartbeat/fencing logic, bounded JobEvent API, isolated parser
executor and tests. No broker package or paid service is needed for local validation.

- Job records always include user_id, project_id, document_id, revision_id, kind,
  state/stage, cursor, attempt/max_attempts, available_at, lease_owner, lease_until,
  monotonic fencing token, idempotency key and cancellation request.
- Claim a small batch with FOR UPDATE SKIP LOCKED; commit before parsing. Do not hold
  a database transaction while processing a book. Heartbeat with a conditional
  owner/fence update. A stale lease must not overwrite a new worker's result.
- At-least-once execution with idempotent writes, not exactly-once marketing:
  deterministic revision/parser keys, bounded retries/backoff, checkpointed sections,
  reconciliation for interrupted DB/vector/storage side effects.
- Cancellation is durable and cooperative between bounded sections. If a native/parser
  child does not stop, supervisor kills and reaps it. Restart/kill worker tests must
  prove recovery without duplicate current revisions or stale vector publication.
- Parser processes get only the specific immutable input and private temporary output,
  minimal environment, denied network, CPU/address-space/output limits and whole-job
  wall-clock budgets. Add tested filesystem/process containment and cgroup/RSS/pid
  budgets before calling this safe for hostile multi-user books. Do not inherit API
  provider/database secrets into the parser. Parent limits alone are insufficient.
- Current local filesystem supports one host. A multi-host worker requires an
  implemented and separately tested object-store provider; never assume the existing
  LocalStorageProvider is shared across hosts.
- Progress derives from persisted stages and verified counts. Show queued, parsing,
  indexing, partial, failed, cancelled and completed honestly; no fabricated percentage.

Acceptance: kill worker mid-chapter, expire/reclaim lease, run two claimers, reject
stale fence writes, cancel/resume, simulate unavailable DB/storage/vector backend,
verify owner isolation, bound event retention and peak resources on a fixed corpus.

## P1.3 — formats, access rights and large inputs

PDF: preserve physical page numbers separately from printed labels, mark OCR text
and confidence, stream/checkpoint bounded page batches, retain immutable revision
provenance. A summary must say when some pages failed.

EPUB: respect spine reading order, OPF/nav/NCX and XHTML sections; never infer fixed
physical pages. Use the existing zipfile/defusedxml boundary where feasible. Reassess
dependencies/licenses before choosing a library (do not casually add AGPL EbookLib).
Reject encrypted/DRM-protected books, DTD/entities, oversized/too-many archive members,
unsafe relative/absolute/file/remote references and zip symlinks. Do not unpack to an
unrestricted filesystem or load remote book assets.

Web: reuse SafeFetcher and current robots/host-folder/budget restrictions. No browser
automation, credentials, paywall bypass or access-control workarounds. Treat robots.txt
as a crawl rule, not a copyright license. Store provenance, acquisition date, license
or owner permission attestation, canonical URL and content version; unknown rights
require a visible review decision. Source text never changes fetching permissions.

Large files: independently enforced compressed/uncompressed/part/page/character budgets,
bounded in-flight documents, streaming extraction/checkpoints, backpressure and honest
partial states. Benchmark a fixed public-domain/authorized corpus with peak RSS,
runtime, temporary disk and queue recovery; set acceptance budgets before expanding
the first-milestone size limit.

## P1.4–P1.6 — learning and mobile behavior

- Retrieval carries immutable document/revision/section/page identifiers through
  chunking, keyword/vector search, SourceRef and the source card. Apply owner/project/
  library filters in both native vector and keyword paths. Empty scope never falls
  back to all files. Cross-source claims cite the actual contributing sources and
  distinguish retrieved evidence from inference or unresolved contradiction.
- Evaluate Uzbek Latin/Cyrillic, English and Russian with labelled relevance/citation
  fixtures. Answer quality, source coverage and citation accuracy are separate metrics.
  Offline keyword mode must remain explicit. A live embedding/model evaluation needs
  a separately approved budget and never runs in ordinary CI.
- Study sets reference an immutable source revision and sections. Reuse existing
  educational output schemas where they fit; flashcards, answer keys, explanations
  and grading are validated separately. Unsupported answer claims are refused or
  labelled. Student scores are not official IELTS/exam certification.
- Learning progress comes from user attempts, explicit completion and review events;
  never infer mastery from time spent or a generated summary. Scope every write/read,
  support reset/delete, and define retention/export behavior before storing habits.
- Mobile UI: Knowledge -> source -> sections -> cited explanation -> practice ->
  progress; server-paginated reading, small bounded responses, visible job/cancel/
  retry states, keyboard/focus/accessibility, uz/en/ru strings and offline errors.
  Test narrow Android/iPhone viewports, long titles, RTL/mixed scripts if supported,
  focus after navigation, stale/deleted source revisions and interrupted uploads.

## Dependency, risk and release gates

P1.1 needs no new dependency, infrastructure or model budget. Later parser libraries,
queue/object storage choices and multi-user authentication require a small ADR,
license/security review and local recovery tests before adoption.

Open P0 native libxml2 risk and incomplete parser filesystem/RSS isolation are not
solved by this roadmap. Rulesets/review authority are owner settings. Do not market
Student V1 as production-ready until those gates and P1 recovery/isolation/quality
acceptance pass. No self-modification, tool installation, repository write, push,
merge or deployment is granted to any Student source, model reply or K3 proposal.
