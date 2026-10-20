# Coordinated P0/P1 — controlled Student foundation

Implementation baseline: `db7b548fb6544c978312d00e971fe1dfa470d35a` (merged PR #13).
Branch: `feat/p0-p1-controlled-student-foundation`. No deployment or ruleset change.

## Verdict and security prerequisite

**BLOCKED for production/native Student ingestion.** This is a safe stored-text
foundation for independent review, not complete PDF/DOCX/EPUB Student V1.
The managed runtime is UID 1000 with a read-only cgroup v2 mount and no delegated
workload control. The current unprivileged API image also has no workload executor.
Neither process groups nor the legacy 4 GiB address-space limit solve D4/D6/D7.
No implementation here claims otherwise or enables an unverified sandbox backend.

Owner decision: select/provide an isolated worker runtime with enforceable per-workload
cgroup v2 memory.max, memory.swap.max=0, pids.max, CPU control and reliable cgroup.kill
(or equivalent whole-workload termination), filesystem/user/network isolation, and a
supervisor which kills orphan workloads after consumer crashes. The executor must
keep itself and its control interface inaccessible to document processes. Never give
the API a privileged Docker socket or writable host root/cgroup tree. A verified
executor would need hostile setsid/double-fork, aggregate RSS/OOM/swap, lease loss,
cancellation, timeout, parent death and crash/restart tests before native enablement.
A runtime decision alone is not authorization to enable parsing or deploy.

## What changed

### Fail-closed execution and honest compatibility

`documents/isolation.py` has no environment switch enabling legacy native execution.
Outside an explicit test-fixture ContextVar, run_native refuses before acquiring its
lock or spawning anything. OCR and Office discovery return unavailable without running
a binary. Production no longer ships Tesseract/LibreOffice; native regression fixtures
retain their tools in the separate `office-tests` target. Python parsing dependencies
remain for compatibility/fixtures; their presence is not execution authorization.

Generic parser dispatch denies PDF, DOCX, XLSX, images and HTML; K1 checks the same
policy before dispatch, including restarted old queued documents. Uploads reject
unsupported formats before ZIP/native inspection and cap safe text inputs at 2 MB.
Organization Word templates and uploaded image decoding enforce the same denial.
The tool registry denies native parsing/rendering tools and removes them from available
names outside fixtures, so K3's registry awareness does not advertise disabled tools.
Errors are fixed messages, not document snippets or host exception traces. This is a
security-required behavior change: native document/visual workflows are intentionally
unavailable until isolation is proven. EPUB remains unsupported and is explicitly
reported as blocked, not silently treated as a PDF/text file.

Controlled unit/integration fixtures enter the exception in tests/conftest.py. Browser
fixtures use tests/e2e_app.py via the explicitly requested scripts/ezo.py api --e2e
launcher. Normal uvicorn, Docker entrypoint and durable worker never enter it. The
harness is not packaged in the production image (.dockerignore excludes tests).
Native fixture tests verify legacy behavior only; they are not proof of production
isolation. Separate regressions reset the fixture context and verify denial, including
attempts to launch setsid and a memory hog without ever spawning them. Those tests
prove fail-closed admission, not containment of running hostile code.

### Durable execution and Student reading

Run a separate consumer, using existing Database/DocumentJobs without brokers or new
frameworks:

```
cd apps/api
uv run alembic upgrade head
uv run python -m ezo_api.knowledge.jobs.worker --worker-id student-local-1
```

Alternatively start the existing local stack/migrations, then opt into the same image's
consumer with `docker compose --profile student up -d student-worker`. This is an
optional local profile, not a deployed service. API/worker containers drop capabilities,
set no-new-privileges, use read-only roots/bounded tmpfs, and set container memory/swap
and PID ceilings. These are container-wide defense in depth for safe text; they do not
create per-document native isolation or close D4/D6/D7 for native execution.

Use a throwaway local database and no provider keys. SQLite supports **one consumer**;
use PostgreSQL for competing workers. The worker does not apply migrations on startup;
operators must run the existing migration command first. Process supervision is an
operator concern; the CLI exits on unexpected database failures so a supervisor can
restart it rather than silently hide failure. No API startup consumer is registered.

The worker polls the existing queue, claims a fresh lease, reads only a bounded pinned
normalized revision (SQL length predicate and enqueue-time hash), creates exact Unicode
paragraph spans and publishes through the existing fenced atomic transaction. Up to
1000 spans; the tail is coalesced, never truncated. It never reads a raw upload, opens a
PDF/ZIP/image, fetches a website, calls a provider or executes generated code.

The whole iteration has a 20-second asyncio deadline inside the 60-second lease;
constructor validation forbids deadlines reaching the lease duration. Timeout consumes
an attempt and uses existing bounded transient retry/backoff; failure cleanup itself
has a five-second deadline. No native workload exists to cancel physically. A crashed
worker leaves a lease for existing expiry/reclaim, generating a new token and attempt.
Lease expiry, owner cancellation and source mutation prevent publication. SIGINT and
SIGTERM stop polling, allow the bounded current iteration to finish, then dispose DB
connections. Force-killed workers rely on lease expiry, never an attempt reset.

Owner HTTP control plane:

- GET `/api/student/status`: truthful formats, limits and unavailable executor reason.
- POST `/api/student/readings`: `{text, title?, project_id?}`; authorized UTF-8 text only,
  reuse K1 storage/normalization/revision/indexing, then enqueue a stored-text job.
- GET `/api/student/readings/{job_id}?project_id=...&offset=0&limit=4000`: existing
  owner/project-authorized SQL-paged immutable publication; original global Unicode
  offsets and pinned revision/hash. Maximum page 8000 code points.
- Existing `/api/knowledge/document-jobs/{id}` and `/cancel` expose status/cancellation.

K1 submission and queue insertion use separate durable transactions. A crash between
them can leave an indexed source without a job; repeating the same text/project request
reuses its revision and idempotently enqueues. It does not revive a terminal job. Normal
text K1 processing still uses its existing runner; this is not a claim that the old
full ingestion pipeline has become a fenced parser worker. Existing embedding settings
still govern optional K1 embeddings; all verification uses fake/offline providers and
no paid API. For strictly offline development leave all provider keys empty.

### Confirmed scope/storage defect

K1's previous duplicate lookup used user_id + content hash, ignoring project. The same
bytes submitted to project B could return project A's document. Duplicate lookup now
requires exact project/null-inbox scope. New upload/URL storage keys also include project
scope, so deleting A does not remove B's independent file. Existing keys remain readable;
no storage backfill or destructive migration. User-wide object deduplication is not
assumed to authorize a different project. Regressions cover separate document IDs,
correct project IDs and surviving B's stored bytes after A deletion.

## Existing job audit and design decisions

PRs #11–#13 provide PostgreSQL document/job SKIP LOCKED, owner-consistent selection,
expiry/reclaim fencing, immutable atomic publication, SQL text pagination and terminal
idempotency. They are retained and exercised by full SQLite/PostgreSQL suites. The new
read_input also checks the lease and source hash before returning bounded text.

No schema migration or dependency was introduced. Migration 0016 private table grants
and uniqueness remain unchanged. Failed/cancelled enqueue never resets attempts. The
explicit generation/root cumulative-budget design in P1_STUDENT_DURABLE_JOBS.md remains
a separate design, not implemented: the deterministic stored-text consumer needs only
existing bounded recovery. Do not claim an explicit owner retry endpoint exists.
Real native/long-running Student V1 still needs the isolated executor, fenced staged
K1 activation, page/section manifest, authorized EPUB parsing and generation migration.
These dependent components stay disabled rather than being implemented atop unsafe
parsing. K3 stays proposal-only; no K4–K7 implementation or autonomous source changes.

## Validation and review

Exact local counts, hosted links, image identity and unsuppressed vulnerability report
are in the final engineering handoff. Earlier reports' scan counts are historical.
Production denial checks replace production native-enable assertions; all existing
native fixture, language-pack, conversion and tini reaping tests remain enabled in the
fixture image. CI/Security gates, severities, Action pins and check names are unchanged.

Review the fail-closed default and fixture-only exception first, then every parser/tool
entry point, project duplicate/storage changes, worker lease/deadline/shutdown behavior,
and the Student submission crash window. Confirm the production image lacks native
executables and reads normalized text only. Independent review and owner approval must
precede any merge; do not deploy this branch.


## Fresh production API scan (local)

Trivy 0.76.0 with the official current GHCR database reports 44 HIGH, 0 CRITICAL,
58 MEDIUM, 61 LOW and 1 UNKNOWN; zero fixable HIGH/CRITICAL. Historical 79 HIGH /
1 CRITICAL applied to the OCR/Office API image, not this new reduced runtime.
No severity suppression, ignored advisory, package-database removal or gate change.
The full raw report and per-advisory list are in the handoff. Base package HIGH
findings remain for util-linux/libmount/libblkid/libuuid/libsmartcols/liblastlog/login/
bsdutils, libacl, ncurses and perl-base. There is no fixed version listed for these
entries in this scan. These libraries/utilities are not used to parse Student input;
non-root/capability restrictions reduce some command paths but do not prove absence
of exploitability. Retain the findings and rescan before any production decision.

Image inspection: lxml 6.1.3, linked and compiled libxml2 2.14.6; no Tesseract/soffice
executables. The old LibreOffice system-libxml2 package is no longer shipped. This
removes that shipped package/exposure, not a claim that all XML parsing is sandboxed.


Direct HTML parsing by the official connector also enforces the same entry-point
policy; it cannot bypass the generic dispatcher guard. A regression prevents calling
trafilatura outside controlled fixtures. The local Docker daemon can enforce container
memory limits (512 MiB and zero swap measured), although the API/worker has no delegated
per-document executor/controller; container-wide limits do not authorize native parsing.
The web runtime now applies signed Alpine stable security upgrades rather than retaining
the known patchable zlib 1.3.2-r0 advisory in the pinned base. Hosted image scans verify
the resulting image; historical local web scans are explicitly identified as such.
