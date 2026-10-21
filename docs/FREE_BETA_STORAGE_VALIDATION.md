# Free-beta adapter/profile: validation and independent-review handoff

Base `d00a1c59e78c9e70c5bf426b2e17f00fcd82b666`;
branch `feat/free-beta-storage-profile`. No schema changes: Alembic head stays 0018.
The [current owner guide](FREE_BETA_STORAGE_PROFILE.md) replaces the old local-disk
blocker assessment. **Live hosting release remains BLOCKED**, not production-ready.

## Verified findings and implementation

| Finding | Evidence and fix |
| --- | --- |
| Local disk prevented ephemeral backend deployment | Added explicit Supabase provider behind StorageProvider; no call-site path rewrites or local fallback. Local production mode still requires a real durable mount; remote mode must pass private bucket, object round-trip and DB policy checks. Full remote mode is not enabled. |
| Office returned nonexistent current-file URLs | Regression captured 404 in `office-before.xml/log`; added owner-scoped current-version download/export aliases through existing immutable version readers. Foreign/current-version pointers cannot cross artifact ownership. |
| Office browser anchors omitted bearer header | Verified JSX links and token-mode denial; Office now uses existing authenticated shared download client and Blob saving. Browser regression asserts Authorization header and no URL token. |
| IELTS session state was mutated in-place | Thirty advances did not complete practice; fixed copied JSON assignment so state persists. Reduced profile does not report word-count-derived/synthetic band or pronunciation scores. |
| Direct Office/IELTS creation accepted foreign conversation IDs | Existing FK alone was not owner authorization. Added shared owner check before render/storage/session creation; regression uses real foreign User/Conversation rows and verifies 404 with no object requests. |
| No reduced authoritative capability boundary | Auth-first default-deny route policy; no raw uploads, tools, model providers, sync/recovery or workers. Status/browser reflect capabilities; typed/forced-agent chat cannot bypass the general offline path. |
| Remote failures could be treated as missing artifacts | Availability/limit errors are distinct and propagated; HTTP 503/413, no provider payload or key disclosure, no empty successful file. Object sizes, immutable writes and canonical artifact SHA256 are checked. |
| SQL policy verification could otherwise target another project | Production free-profile DB endpoint/username must identify the same Supabase project as Storage. Privileged roles and membership in privileged roles are refused before migration and at post-migration startup. |
| Free-host resource and cancellation risk | Small SQL pool, bounded requests/transfers/exports, single physical Office render slot that survives HTTP cancellation. No claim that this constitutes a sandbox or a sustained capacity benchmark. |

Authoritative code: `storage/supabase.py`, `storage/__init__.py`, `free_beta.py`,
`security/edge.py`, `deployment.py`, `main.py`, `api/ownership.py` and direct API
consumers. `deploy/free-beta.env.example` and `deploy/render-free-beta.yaml` are
review-only inputs, not a live configuration. CI/Security include this review branch;
no threshold, audit, auth or isolation rule was disabled.

## Independent review status and remaining risks

**No separate independent reviewer has approved this new patch.** Findings above are
implementation findings backed by code/tests, not a fabricated Claude audit. Existing
independent-review concerns around native descendant containment, budgets and
cancellation are not closed by this profile. Native execution remains disabled here;
full-profile native-host safety requires separate review.

Required independent review focus:

- HIGH: Storage REST server credential has project-wide authority, not bucket-scoped
  least privilege. Dedicated project, backend-only secret and client-policy denial
  are mandatory; compromise still exposes the project's objects/auth authority.
- BLOCKER: Current Free availability, billing/overage behavior, Vercel production URL
  privacy, provider inactivity/retention and actual capacity have not been verified.
  Official sites returned network-policy 403; historic quotas are not current quotes.
- BLOCKER: No live Supabase verified-TLS session, real Storage access/RLS proof,
  cloud restart/restore, or genuine matched DB/object backup has run. No credentials
  or infrastructure were created to pretend these checks passed.
- MEDIUM: No distributed SQL/object transaction or durable cleanup/outbox. A failed
  DB commit after successful object upload may retain a private orphan. Destructive
  artifact mutations are blocked; old local storage migration and automatic GC are
  not implemented. Quota monitoring/backup is an operator requirement, not a hard
  global byte-quota implementation. Large metadata datasets/exports need separate
  capacity review; this is a small-owner profile.
- MEDIUM: Full-access owner browser token remains localStorage-based. No HttpOnly
  login/session redesign, public signup or multi-user launch is claimed.
- Native regression first-run failure is retained below; a successful retry does not
  establish a dedicated production executor or erase environmental sensitivity.
- Container advisories are not suppressed; see the actual scan register/results.

## Local evidence

Evidence directory `/workspace/free-beta-evidence/`; final handoff includes raw XML,
logs, vulnerability JSON, source contract snapshots and exact SHA/PR/hosted outcomes.
No real provider, model quota, production secret or paid service was used.

| Check | Actual local result |
| --- | --- |
| Backend SQLite | 981 passed, 0 failed, 33 skipped |
| Backend PostgreSQL/pgvector | 991 passed, 0 failed, 23 skipped |
| Final PostgreSQL focused regressions | 80 passed, 0 failed/skipped; includes final privileged-membership rejection |
| Ruff / format / mypy | Passed; 447 formatted files, 304 typed source files |
| Frontend lint / types / production build | Passed |
| Frontend unit tests | 68 passed (58 web, 10 shared) |
| Playwright desktop/mobile | 38 passed, 0 failed/skipped |
| Native container regressions | 22 passed on complete retry; first-run failures retained below |
| Alembic / database privileges | Disposable PostgreSQL upgrade through 0018 and migration check passed |
| Python / Node production dependency audit | 80 Python packages, zero known advisories; Node zero advisories |
| Secret scan before final commit | 154 commits, zero leaks; final committed scan recorded in handoff |
| API Docker build | Passed, final image `sha256:15fc081f6a00a0dcadef4f1bcc3e63fd45f5f7aaddb0b4c735882d62aea75e3a` |
| API Trivy | 44 HIGH, 0 CRITICAL, 0 fixable HIGH/CRITICAL in current database; no suppressions |
| Web Docker build | BLOCKED locally: Alpine signed APK endpoint returned 403, build exit 99; no trust bypass |

Full backend suites preceded the final privileged-membership SQL branch; the final
80-case PostgreSQL regression run and lint/type checks ran afterward. The image was
rebuilt from that final source. Native/parser dependencies were unchanged.

Actual image runtime: certifi 2026.10.19, lxml 6.1.3, compiled/runtime libxml2 2.14.6,
OpenSSL 3.5.7. Trivy database UpdatedAt `2026-10-21T01:19:53.032404989Z`;
scan completed 2026-10-21 13:10 UTC. Lower severities: 58 MEDIUM, 61 LOW, 1 UNKNOWN.

A network-disabled, read-only container component smoke with 512 MiB memory and
0.1 CPU completed bounded DOCX/XLSX generation: cgroup memory peak 199,516,160 bytes,
2.402 seconds, outputs 36,878 / 12,856 bytes. This used test mode, no remote SQL or
HTTP handshake, and is neither a sustained capacity test nor production startup proof.

Native first run: **3 passed, 19 failed**. The cancellation fixture's workload did not
start within its wait deadline; a labelled, never-started `created` reservation stayed
behind and later cases conflicted/busy-failed. Its exact image/labels/state were
recorded, then **only that stopped task-owned container** was removed without force.
Complete rerun: **22 passed, 0 failed/skipped**. No native harness deadline, admission
rule or isolation check was weakened. Resource contention is plausible, not a proven
root cause. No native capability is enabled by this result.

Earlier focused failures also remain available: Office current download returned404;
the initial IELTS progression test never completed; a fixture initially used an
incorrect User keyword (test corrected). These are not counted as passing attempts.

Storage tests use an HTTP transport fixture grounded in actual upstream routes,
not a provisioned Supabase service. API recreation tests share the external fixture
and same SQL database while changing the API's unused local storage root. They prove
there is no local-file dependency in these code paths; they do not prove cloud SLA,
Free retention, backups or live RLS. Actual PostgreSQL catalog checks run separately
against disposable databases, including RLS-off, public-policy, privileged-role and
privileged-membership rejection.

Supabase Storage source inspected at commit
`6a2aaee8acdd39d9bc59bcc3282528d613d37dbc`:
[bucket metadata](https://github.com/supabase/storage/blob/6a2aaee8acdd39d9bc59bcc3282528d613d37dbc/src/http/routes/bucket/getBucket.ts),
[object writes](https://github.com/supabase/storage/blob/6a2aaee8acdd39d9bc59bcc3282528d613d37dbc/src/http/routes/object/createObject.ts),
[reads](https://github.com/supabase/storage/blob/6a2aaee8acdd39d9bc59bcc3282528d613d37dbc/src/http/routes/object/getObject.ts),
[HEAD](https://github.com/supabase/storage/blob/6a2aaee8acdd39d9bc59bcc3282528d613d37dbc/src/http/routes/object/getObjectInfo.ts),
[deletes](https://github.com/supabase/storage/blob/6a2aaee8acdd39d9bc59bcc3282528d613d37dbc/src/http/routes/object/deleteObjects.ts).
Hosted Storage gateway/version/credential compatibility is still an acceptance gate.

## Hosted checks

Final exact-head CI and Security URLs/status are in the final handoff/evidence bundle.
Local counts are not hosted counts; unavailable hosted artifacts are not invented.
No deploy workflow, worker service, paid plan, secret generation or merge action was
added or executed. Owner independent review and explicit approval remain required.

## Unpatched HIGH container advisory register

| Package | Installed | Advisory | Severity | Fixed |
| --- | --- | --- | --- | --- |
| bsdutils | 1:2.41.5-0+deb13u1 | CVE-2026-76642 | HIGH | not provided |
| bsdutils | 1:2.41.5-0+deb13u1 | CVE-2026-78408 | HIGH | not provided |
| bsdutils | 1:2.41.5-0+deb13u1 | CVE-2026-78409 | HIGH | not provided |
| bsdutils | 1:2.41.5-0+deb13u1 | CVE-2026-78410 | HIGH | not provided |
| libacl1 | 2.3.2-2+b1 | CVE-2026-54369 | HIGH | not provided |
| libblkid1 | 2.41.5-0+deb13u1 | CVE-2026-76642 | HIGH | not provided |
| libblkid1 | 2.41.5-0+deb13u1 | CVE-2026-78408 | HIGH | not provided |
| libblkid1 | 2.41.5-0+deb13u1 | CVE-2026-78409 | HIGH | not provided |
| libblkid1 | 2.41.5-0+deb13u1 | CVE-2026-78410 | HIGH | not provided |
| liblastlog2-2 | 2.41.5-0+deb13u1 | CVE-2026-76642 | HIGH | not provided |
| liblastlog2-2 | 2.41.5-0+deb13u1 | CVE-2026-78408 | HIGH | not provided |
| liblastlog2-2 | 2.41.5-0+deb13u1 | CVE-2026-78409 | HIGH | not provided |
| liblastlog2-2 | 2.41.5-0+deb13u1 | CVE-2026-78410 | HIGH | not provided |
| libmount1 | 2.41.5-0+deb13u1 | CVE-2026-76642 | HIGH | not provided |
| libmount1 | 2.41.5-0+deb13u1 | CVE-2026-78408 | HIGH | not provided |
| libmount1 | 2.41.5-0+deb13u1 | CVE-2026-78409 | HIGH | not provided |
| libmount1 | 2.41.5-0+deb13u1 | CVE-2026-78410 | HIGH | not provided |
| libncursesw6 | 6.5+20250216-2 | CVE-2025-69720 | HIGH | not provided |
| libsmartcols1 | 2.41.5-0+deb13u1 | CVE-2026-76642 | HIGH | not provided |
| libsmartcols1 | 2.41.5-0+deb13u1 | CVE-2026-78408 | HIGH | not provided |
| libsmartcols1 | 2.41.5-0+deb13u1 | CVE-2026-78409 | HIGH | not provided |
| libsmartcols1 | 2.41.5-0+deb13u1 | CVE-2026-78410 | HIGH | not provided |
| libsystemd0 | 257.13-1~deb13u1 | CVE-2026-16742 | HIGH | not provided |
| libtinfo6 | 6.5+20250216-2 | CVE-2025-69720 | HIGH | not provided |
| libudev1 | 257.13-1~deb13u1 | CVE-2026-16742 | HIGH | not provided |
| libuuid1 | 2.41.5-0+deb13u1 | CVE-2026-76642 | HIGH | not provided |
| libuuid1 | 2.41.5-0+deb13u1 | CVE-2026-78408 | HIGH | not provided |
| libuuid1 | 2.41.5-0+deb13u1 | CVE-2026-78409 | HIGH | not provided |
| libuuid1 | 2.41.5-0+deb13u1 | CVE-2026-78410 | HIGH | not provided |
| login | 1:4.16.0-2+really2.41.5-0+deb13u1 | CVE-2026-76642 | HIGH | not provided |
| login | 1:4.16.0-2+really2.41.5-0+deb13u1 | CVE-2026-78408 | HIGH | not provided |
| login | 1:4.16.0-2+really2.41.5-0+deb13u1 | CVE-2026-78409 | HIGH | not provided |
| login | 1:4.16.0-2+really2.41.5-0+deb13u1 | CVE-2026-78410 | HIGH | not provided |
| mount | 2.41.5-0+deb13u1 | CVE-2026-76642 | HIGH | not provided |
| mount | 2.41.5-0+deb13u1 | CVE-2026-78408 | HIGH | not provided |
| mount | 2.41.5-0+deb13u1 | CVE-2026-78409 | HIGH | not provided |
| mount | 2.41.5-0+deb13u1 | CVE-2026-78410 | HIGH | not provided |
| ncurses-base | 6.5+20250216-2 | CVE-2025-69720 | HIGH | not provided |
| ncurses-bin | 6.5+20250216-2 | CVE-2025-69720 | HIGH | not provided |
| perl-base | 5.40.1-6+deb13u1 | CVE-2026-9538 | HIGH | not provided |
| util-linux | 2.41.5-0+deb13u1 | CVE-2026-76642 | HIGH | not provided |
| util-linux | 2.41.5-0+deb13u1 | CVE-2026-78408 | HIGH | not provided |
| util-linux | 2.41.5-0+deb13u1 | CVE-2026-78409 | HIGH | not provided |
| util-linux | 2.41.5-0+deb13u1 | CVE-2026-78410 | HIGH | not provided |
