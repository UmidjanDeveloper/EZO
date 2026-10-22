# Zero-budget private-beta evidence

Audited base/default integration: `6e610b20627d591a8be83dad7fed6b79ccc7beb0`
(PR #18 merged; Alembic head 0018). Review branch:
`feat/zero-budget-private-beta`. No provisioning, live cloud connection, production
secret creation, paid model call, deployment, ruleset change or merge was performed.

**Hosted launch verdict: BLOCKED.** The [owner checklist](ZERO_BUDGET_PRIVATE_BETA.md)
is a preparation plan with explicit gates, not permission to deploy.

## Significant findings and evidence

| Severity | Finding | Evidence / decision |
| --- | --- | --- |
| BLOCKER, confirmed | No verified durable free API file store | `storage/local.py` is filesystem storage; `deployment.check_storage()` requires a mounted durable path. Newly built production image exits 1 on the ephemeral filesystem with otherwise valid production inputs, before migration/network access. Supabase object-storage adapter does not exist. No guard bypass. |
| BLOCKER for native features | Render/Vercel do not establish the required dedicated executor | `student/worker.py` requires explicit dedicated-host acknowledgement and PostgreSQL; `documents/executor/controller.py` requires Docker isolation and daemon-wide admission. No native API switch, socket mount or new worker service added. Raw-job upload is not extraction. |
| HIGH, verification gap | Current free-plan, private production-UI protection and billing terms unverified | Official Render/Supabase/Vercel hosts return proxy 403. Historic planning figures are explicitly unverified. Hobby entitlement is not a guarantee of owner-only access to a production URL. |
| HIGH, confirmed residual | 44 HIGH OS-package advisories | Rebuilt image and current cached Trivy DB; full affected package/version/advisory register below. Zero known fixes reported is not zero risk or practical-unreachability evidence. |
| HIGH, operational | Backups and real Supabase TLS/ACLs not validated live | Local PostgreSQL 16 + vector tested with limited role; real provider CA, session endpoint, inactivity recovery, backup/restore and resource quotas remain owner gates. |
| MEDIUM, confirmed behavior | IELTS estimates are heuristics | `api/routes/ielts.py` completion derives scores from word count and assigns pronunciation 6.0. Not validated speech assessment; documented without expanding this deployment PR into product redesign. |
| MEDIUM, confirmed behavior | Owner credential in browser localStorage | Full-access single-owner token; browser/device/XSS risk persists. No new frontend secret or public data API added. |
| MEDIUM, operational | In-process recovery/rate limits and durable worker need lifecycle planning | One process/replica; sleeping hosts interrupt work and reset process-local budgets. Stored-text worker is not automatically started by API. Native execution remains separate and disabled operationally. |

## Changes

- `README.md`: current blocked zero-budget decision and optional offline AI configuration.
- `docs/ZERO_BUDGET_PRIVATE_BETA.md`: free hosting matrix, honest offline feature
  matrix, 0018 database/TLS/backup gates, exact environment names, mobile owner
  checklist, rollback and separately approved paid path.
- Old private-beta/mobile runbooks: clearly superseded; old native-in-API and
  nondurable-job descriptions must not be followed.
- Root `render.yaml` moved to `deploy/render-paid-reference.yaml`: explicitly paid,
  outside default Blueprint discovery; no automatically selected paid plan.
- `deploy/private-beta.env.example`: future durable host only, all model credentials
  empty, auxiliary provider/native settings disabled, conservative positive limits.
  Zero daily limit would disable limiting, not disable spending.
- `tests/integration/test_deployment.py`: production-policy app with no provider;
  11 merged workspace endpoints × missing/wrong token = 22 negative requests with
  malformed body all return 401 without needing a real database/provider.
- CI and Security push branch allowlists include this review branch. No check,
  severity threshold, authorization or isolation rule relaxed.

## Local validation

Evidence directory: `/workspace/zero-budget-evidence/`. Counts and hosted status
are finalized below after running checks. No real provider keys are used; model
responses in tests are fixtures. Local native tests are not Render compatibility.

| Check | Local result |
| --- | --- |
| Focused deployment checks | 7 passed, 0 failed/skipped |
| Full SQLite (OCR/Office required) | 932 passed, 0 failed, 32 skipped |
| Full PostgreSQL/pgvector (OCR/Office required) | 941 passed, 0 failed, 23 skipped |
| Real-container PostgreSQL native cases | 22 passed, 0 failed/skipped on complete rerun (includes 5 Student cases) |
| Frontend/shared unit tests | 68 passed, 0 failed (58 web + 10 shared) |
| Playwright desktop/mobile | 35 passed, 0 failed/skipped |
| Python quality | Ruff pass, 442 formatted files; mypy 301 source files pass |
| Frontend quality/build | Lint, typecheck and production Next.js build pass |
| SQLite/limited-role PostgreSQL migration + drift | Upgrade head 0018 and `alembic check` pass; disposable PG downgrade 0017/upgrade 0018 pass |
| API Docker | Build pass; hosted-mode/ephemeral-storage refusal pass (2 scenarios); health/auth/real-volume restart smoke pass (test mode + SQLite) |
| Web Docker | FAILED locally: signed Alpine APK indexes blocked by proxy HTTP 403, exit 99. No fallback, trust bypass or security upgrade removal; no new web image available to scan locally. |
| pip-audit / pnpm production audit | 80 Python packages: 0 advisories; Node: 0 vulnerabilities at all reported levels |
| gitleaks | Existing 153-commit history: 0 leaks; final commit scanned separately before push |

SQLite skips: 22 native cases (run separately), 10 PostgreSQL-only cases. PostgreSQL
skips: 22 native cases (run separately), 1 SQLite-only development contract. Actual
container tests use real PostgreSQL on a separate disposable database and pinned
fixture images `sha256:a764d7b2dfd37cb0ad4245ebd7d0e07a6d0130e847f7281471fac235f72dcbd0`
and `sha256:84c0d901d50a17abd296e23bc3dc796210b73554d9d2755b1e74707aadcff9c2`.
These previously built fixtures are reused: executor/worker sources and dependency
lockfile are unchanged from the verified Student head; they are not a newly built
Render worker or proof of dedicated-host production safety.

Failed/interrupted first attempts are retained in the evidence bundle. Docker build
pressure caused ENOSPC during initial PostgreSQL/E2E runs; those attempts are not
passes. Scoped task-owned build cache was removed, then full suites were rerun.
The first native run had 21 passed/1 failed (expiry recovery returned 409 instead of
200); focused expiry retry passed. Disk pressure coincided with the first run, but
causation is not proven and the failure is not suppressed. The complete subsequent
container rerun passed all 22 cases; no test or source was changed to obtain that result.

Hosted CI/Security: use the review branch's exact-head Actions runs, linked in the
final handoff and evidence bundle. Local results above are not hosted results;
no hosted artifact counts are inferred from green badges. No production deploy
workflow has been added.

Production API image: `sha256:e0aa7e7dee8ad28c289df280de91576de71f92cf0f60d704bab1694dc8c09033`.
Runtime: certifi 2026.10.19; lxml 6.1.3; compiled/runtime libxml2 2.14.6;
OpenSSL 3.5.7. This describes the actual rebuilt image, not host Python packages.
No libxml2 advisory is reported by this scan; that is not a universal parser-safety claim.

Trivy 0.76.0 database UpdatedAt `2026-10-21T01:19:53.032404989Z`,
NextUpdate `2026-10-22T01:19:53.032404708Z` (current at scan time).
Severity totals: 44 HIGH, 0 CRITICAL, 58 MEDIUM, 61 LOW, 1 UNKNOWN;
**0 fixable HIGH/CRITICAL**. No advisory was ignored or suppressed by this PR.

Local Supabase-shaped PostgreSQL validation: admin creates vector under `extensions`;
checked-in role script creates limited `ezo_app`; migrations and drift check run as
that role through 0018; disposable-only downgrade 0017/upgrade 0018 also succeeds.
`ezo_app`: superuser/create-db/create-role/bypass-RLS/replication all false, connection
limit 20. `anon`/`authenticated`: no effective table/column access to `users`,
`personal_goals`, `student_raw_revisions`; PUBLIC table grant query returns zero
rows. This database is explicitly disposable and loopback-only. No live Supabase
connection or TLS handshake was performed. Tests do not establish cloud backups.

## Remaining unpatched image findings

Repeated advisory IDs across packages are retained as reported, not deduplicated
away to understate the affected-package count. `not provided` means the scanner
reports no fixed version for that package at this database revision.

| Package | Installed | Advisory | Severity | Fixed version |
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
