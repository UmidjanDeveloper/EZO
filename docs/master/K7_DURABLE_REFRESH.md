# K7 governed refresh — backend implementation candidate

This implements the P6 refresh contract in the owner-supplied P0–P9 roadmap.
It does not finish P0–P9, enable K4 execution, or authorize deployment. Existing
Student jobs/revisions and all eight upstream requirements remain intact.

## Scope and state transitions

Existing source registration/first reading stays compatible. Explicit refresh now
uses durable `source_refresh_runs`, not a per-request background task. The old
`POST /api/learning/sources/{id}/refresh` adapts to this queue; new clients use
`POST .../refresh-runs` with a stable UUID `request_id` for replay safety.

A source has at most one queued/running run (unique active key). A request ID
always returns the same run, including terminal failure/cancellation; terminal
attempt counts are never reset. An owner can explicitly request a new UUID after
a terminal result. Each run admits at most three attempts. Only storage/deadline
interruptions use delayed retries; unexpected failures are not called successes.
An expired running attempt can be reclaimed with a new token; old tokens cannot
publish, fail, cancel, or replace the new worker's result.

Fetch permission and recurring consent are separate from source text. A one-shot
owner refresh grants no recurring schedule. A confirmed schedule has an interval
between one hour and30 days. Policy changes increment a generation and cancel
active work. Revocation fences new request admission and publication. Already
admitted/in-flight HTTP/provider operations cannot be unsent. Admission is checked
before every HTTP hop (including robots/redirects) and embedding batch. Previously
stored owned knowledge is retained and labelled; delete remains a separate action.

The scheduler durably coalesces missed intervals into one observation, rechecks
under locks and creates no catch-up storm. A history quota of10,000 runs per owner
uses a real owner-row admission lock across sources; quota failure is explicit.
No automatic history deletion, quota reset or invisible permission grant occurs.

## Publication and storage boundaries

1. Queue snapshot binds source identity, owner/project scope, limits, permission
   generation and current document fingerprints. No source bodies/secrets enter it.
2. Fetch, bounded parsing, chunking and embedding run outside SQL publication locks.
   Existing SSRF, robots, source readers and provider abstractions are preserved.
3. Raw blobs use immutable per-run/per-attempt keys. A durable cleanup entry is
   committed before each put; the stored checksum is verified before publication.
4. One SQL transaction locks source/policy/run/documents, revalidates input and
   authority, writes revisions/chunks/vectors, updates source state, stores the
   bounded version manifest/audit and completes the run. The database clock is
   checked again after vector writes. Failure rolls back all document publication.
5. A complete fetch withdraws disappeared URLs from current search while retaining
   immutable historical revisions. A partial fetch never treats unseen content as
   deleted or freshly verified; retrieval labels it as possibly stale.
6. Unpublished blobs are cleaned only after their attempt deadline plus grace;
   published/document/revision references are protected. Cleanup tombstones remain
   and are retried so a delayed stale writer cannot silently leave a permanent
   abandoned object. Source deletion preserves uncommitted cleanup entries.

Cleanup performs a bounded provider delete while holding its source/blob locks;
this is an explicit contention tradeoff, not a distributed SQL/object transaction.
Run cleanup consistently in the selected hosting environment. Journal/backup restore,
provider retention and disk quotas still need operational acceptance. A database
restored without matching object storage is not a valid complete backup.

The shared historical-key deletion regression is also fixed in the existing
KnowledgeService: deleting a document checks both current documents and historical
revisions before removing a content-addressed blob used by another source.

## Resource and parser policy

One worker cycle at a time per process; SQL leases also isolate independent workers.
Whole-attempt time is the owner's bounded source limit (10–1800 seconds), with a
fixed lease grace, no unbounded heartbeat. Hard caps:200 documents,20 MB network/
source bytes,2 MB per parsed document,5 million normalized characters,2,000 chunks,
500 HTTP admissions and4,096 dimensions per vector. No native sandbox guarantee
or provider-side dollar cap is implied. Provider calls can cost money when the
operator configures real keys; tests use deterministic providers only.

Production web pages use `bounded-html-text/v1`: Python HTMLParser, explicit byte/
event/depth/section caps, no JavaScript, external resources or native XML parsing.
It extracts body text/heading boundaries; it does not reproduce rendered layouts,
CSS visibility, table/formula semantics or JavaScript-only content. Metadata records
this coverage. The old trafilatura path remains limited to controlled native test
fixtures. Native PDF/DOCX/EPUB/OCR/Office ingestion still requires the separately
reviewed executor; no parser fallback is enabled inside the API for these formats.
A refresh that needs an unsupported parser fails explicitly and preserves the
previous publication. Initial K1 source reading still uses its existing recovery
runner; replacing that first-read implementation is not claimed here.

## Additive API contract for Antigravity

All paths below start `/api/learning/sources/{source_id}`. Current authentication,
rate limits and source ownership apply; wrong-owner resources return404. No model
or retrieved content has permission to invoke these controls autonomously.

| Method/path | Request | Result |
|---|---|---|
| `PUT /refresh-permission` | `enabled`, optional `interval_seconds`, `confirm:true` | generation/next run; confirmed changes fence active work |
| `GET /refresh-permission` | none | governed flag, permission and recurring consent |
| `POST /refresh-runs` | stable UUID `request_id` |202 durable run; terminal replay does not restart |
| `GET /refresh-runs` | limit1–20, bounded offset | owned runs and actual bounded manifests |
| `POST /refresh-runs/{run_id}/cancel` | none | cancellation if active; completed/failed remain truthful |
| `GET /freshness` | none | last observation, overdue/failure/revocation state; no guessed remote changes |

The existing `/versions` pagination and its three-key document provenance entries
remain compatible; new v2 entries add actual run/attempt/generation context. Global
revision offsets and original content hashes are preserved. The UI should render
queued/running/failed/partial/cancelled independently; a completed run can describe
a partial source. Antigravity implementation/review is pending; no UI files changed.

## Local/operator command and rollback constraints

For a separately reviewed full profile, the explicit worker entry point is:

```sh
python -m ezo_api.learning.refresh_cli
```

This command is not auto-started by the API or Docker entrypoint. It validates the
same environment/TLS/DB role/startup policy as the API and refuses free-beta or
disabled learning. No service was provisioned or started against real sources.
SIGTERM/SIGINT cancels and joins owned tasks; the durable expired lease recovers an
interrupted attempt without resetting budgets. The global learning-off switch also
prevents legacy recovery from issuing new fetches in this candidate.

Migration0020 is additive after0019. Stop workers before schema changes. Do not
roll back to an old binary that ignores refresh policies while leaving source
reading active; keep a permission-aware patched binary or keep the service stopped.
Never downgrade permission/history tables to revive work. Test restores with the
matching objects, migration revision, private grants and revoked permissions before
an owner-authorized release. No automatic merge/deploy or live cloud acceptance.

Regression files: `test_governed_refresh.py`, `test_refresh_poll.py`,
`test_bounded_html_text.py` plus the preserved `test_learning.py` suite. Exact local
and hosted results belong to the evidence report, not an assumed green label here.


## Parser change and K3 cache integrity

An unchanged raw input hash does not prove unchanged extraction. When a parser
produces different normalized text, KnowledgeService creates a new revision and
preserves the old text/chunks rather than binding new chunks to an old text body.
The original byte hash stays unchanged; normalized text digest/extractor metadata
records the transform. A real trafilatura-to-bounded-HTML fixture regression failed
before this correction. Explicit reindex/deletion and completed source reads
invalidate K3's cached proposals, which must not outlive their actual evidence.
K3 remains proposal-only; no generated instruction gains action authority.


Standalone worker startup explicitly checks the application's non-privileged DB
role before providers are built, verifies public-table restrictions and requires
the exact migration head for its reviewed code. The API/migration owner performs
the migration; a worker never auto-upgrades a shared database while polling.
The whole-attempt async deadline fences publication and cancels awaited work;
bounded pure-Python parser threads can finish cooperatively. It is not a hard
OS CPU sandbox or a substitute for K4. Freshness distinguishes a failed first read
(`not_indexed`) from an actual indexed observation.
