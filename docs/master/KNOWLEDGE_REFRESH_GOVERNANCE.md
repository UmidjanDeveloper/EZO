# K7 refresh audit and recovery prerequisite

Historical baseline audit below. The continuation now implements the durable
refresh transaction/permission/schedule/journal design in
[K7_DURABLE_REFRESH.md](K7_DURABLE_REFRESH.md); this historical list must not be
read as a claim that all those implementation items are still absent. Independent
review, actual hosting/backup acceptance and native worker gates remain open.

Base: externally merged PR25, cd9bbd0633022885ef429929a52228146dc51408.
This work preserves Student document jobs, all eight upstream requirements and
existing knowledge citation/revision contracts. It is not a claim of durable K7.

## Confirmed restart defect and implemented recovery

`LearningService._run` commits document registration, then calls `KnowledgeService.ingest`,
which commits `processing` before parsing/indexing. A cancellation/crash at either
boundary leaves unchanged input queued/processing. Startup recovery rereads the
source, but previously skipped any duplicate content, so the index never appeared.
Two regression cases failed against cd9bbd0 with precisely these committed states.

Content deduplication now skips reindexing only when there is no interrupted
queued/processing work to resume. Healthy indexed/partial results keep their
revision IDs and citations. Unchanged failed/needs_ocr states are not implicitly
revived, and existing durable DocumentJob attempts are untouched. A changed input
still follows the existing new-content path. Cancellation after actual index commit
is also tested: recovery preserves that completed revision instead of rebuilding it.

Tests use real migrated SQLite/PostgreSQL databases and the actual ingestion/vector
pipeline, with controlled crash points and a deterministic network/provider fixture.
They do not claim a real website, provider or production crash drill.

## Why a queue wrapper is insufficient

The next K7 implementation needs the following coherent changes together:

1. Owner-scoped source fetch permission generations, explicit recurring schedule
   consent, and revocation. Revocation must fence later publication and new fetch
   admission; an already admitted/in-flight HTTP request cannot be unsent.
2. Durable queued/running/completed/failed/cancelled run records with immutable
   input identity, bounded attempts, lease tokens, real database-clock expiry and
   conditional publication. PostgreSQL requires real SKIP LOCKED contention tests.
3. Staging/parsing/embedding outside the publication transaction; source and job
   authorization checked under a consistent lock order at each publication commit.
   A final lease check alone cannot undo previous per-document commits.
4. Existing `KnowledgeService.ingest` commits internally and flushes chunks before
   awaiting embeddings. Merely adding a source-row lock would hold locks over
   network work (especially the whole SQLite writer lock), harming revocation.
5. Index vectors in both existing stores are SQL-transactional, so they can share
   a fenced publication commit. Physical blob writes/deletes are not transactional.
   Immutable staging plus failure cleanup/outbox is needed; stale work must never
   delete a blob still referenced by a valid revision after rollback.
6. Atomic job/source finalization and honest complete/partial manifests; cancelled
   or stale work must not fabricate a source-version completion. Explicit retries
   create proper bounded lineage rather than resetting terminal attempts.
7. Bounded queue/worker admission, durable periodic scheduling, runtime shutdown,
   backup/restore and resource validation on the actual chosen hosting profile.

These are unimplemented engineering requirements, not waived by the recovery fix.
K4 general execution remains disabled; no parser/sandbox shortcut, autonomous code
execution, remote service, paid API call, merge or deployment is introduced here.

## Additional concurrency prerequisite: one index per pending input

Recovery validation reproduced another failure: two ingestion runners could enter
the pipeline for the same processing input and rewrite its completed revision's
chunk set. The new regression failed before serialization. This is reachable
through independent background/startup runners; a local semaphore in one runner
is not a cross-runner lock.

`KnowledgeService.ingest` now acquires a database write lock and refreshes the row
at both transaction boundaries. PostgreSQL locks the document row; SQLite uses a
real writer lock rather than pretending FOR UPDATE works. A completed or terminal
row is returned without reindexing. Explicit API reindex already queues the row,
so it remains supported. The existing committed processing progress is retained;
the second lock is held through parsing/index publication. If another runner
completed while waiting, it reuses that result. After an error rollback, state
is rechecked under the lock before writing failure, protecting a newer success.

Learning passes the expected source content hash. Replacement input between
processing and publication raises a superseded-input signal, leaves the new input
queued/healthy and creates no false failed result or source completion manifest.
A controlled owner upload between the real commits verifies this on both databases.

This is document-level serialization, not a source lease or full K7 fencing. It
retains the legacy pipeline's write transaction over embedding work; staged
embedding/publication remains necessary for efficient locks and source revocation.
No claim of database-level parallel writer throughput on SQLite, general sandbox
containment, durable schedules or multi-source atomic snapshots is made.

Expected-hash checks also bind ingestion to the actual stored bytes: a corrupted
blob or incorrect restore must fail the integrity check before parsing and must
not publish new chunks under the old registered hash. This is ingestion-time
integrity, not a claim of an already completed backup/restore drill.

## Local storage write prerequisite

The shared `<key>.tmp` rename source caused identical concurrent puts to race;
a failed replacement left a partial temp file. Both failures were reproduced with
actual filesystem writes. Local storage now gives each writer a securely created
0600 temp file in the destination directory, flushes/fsyncs its bytes, atomically
replaces the destination and removes its own temp on failure. Prior target data
survives a failed replacement. APIs/storage keys do not change. Independent native
jobs still receive their authorized staged input, not the private parent volume.

This does not provide persistence on an ephemeral host, a distributed SQL/object
transaction, crash orphan collection or a filesystem power-loss guarantee. Those
hosting/cleanup/backup gates remain explicit. No public storage fallback added.
