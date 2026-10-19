# Private beta hardening: validation and release checklist

Date: 2026-10-19. Verified base: 422beabca8d9d6f96118cd5adc8b0cc2550a781e.
Branch: fix/final-private-beta-hardening, targeting claude/gifted-goodall-bpf01s.
No live production credentials, provider calls or paid resources were used.

## Current results: local cloud workspace

| Check | Exact completed result |
| --- | --- |
| Ruff lint and format | Passed; 389 Python files formatted correctly |
| Mypy | Passed; 269 source files |
| SQLite full backend suite | **780 passed, 5 skipped**, 162.88 s |
| PostgreSQL 16 + pgvector full suite | **785 passed**, 235.47 s; no skips/failures |
| K3 final no-execution/network/cache regressions | **5 passed**, 2.15 s; registry unchanged and nonempty proposal assertions retained |
| PostgreSQL effective privileges + native pgvector scope regressions | **4 passed**; PUBLIC table/column grants rejected, other-owner/project/doc IDs excluded |
| Office relationship bypass fixtures | **6 failed before / 6 passed after** the parser fix |
| Non-root image-native OCR/Office/security tests | **28 passed**, 17.21 s, UID 10001; same native packages as production |
| Alembic | Fresh limited ezo_app login upgraded through **0015**; alembic check found no new upgrade operations |
| Frontend lint + workspace TypeScript | Passed |
| JavaScript unit tests | **65 passed**: 55 web + 10 shared |
| Complete Playwright suite | **31 passed**, 2.0 min; desktop plus phone project; nonce CSP, chat, files, memory, K3, IELTS, presentation and voice flows |
| API and web production Docker builds | Passed; frozen locks, pinned base digests and verified TLS retained |
| Production API smoke | Passed: locally trusted PostgreSQL verify-full TLS, migrations 0015, PORT=10000, UID 10001, Uvicorn PID 1, owner 401/200, docs 404 and CORS allow/reject |
| Durable file smoke | Passed: remove/recreate API with same named volume and database; document content survives and reindex reads retained upload; offline keyword mode, partial/1 chunk |
| Production web smoke | Passed: homepage 200, nonce CSP, no-store runtime JavaScript contains only public API origin |
| Python runtime dependency audit | **0 known vulnerabilities**; pinned pip-audit 2.10.1, includes new defusedxml dependency |
| Node production audit | **0 vulnerabilities**, 206 dependencies |
| Node full development audit | **1 HIGH**, braces 3.0.3, CVE-2026-93687; no published patch in advisory; ESLint-only path, absent from production image |
| Full-history gitleaks | Passed; 0 leaks; existing single synthetic-fixture fingerprint retained, no new suppression |
| Trivy API before → after | **83 HIGH / 1 CRITICAL → 79 HIGH / 1 CRITICAL**; 4 fixable build-tool findings removed; 0 remaining fixable HIGH/CRITICAL |
| Trivy web | **0 HIGH / 0 CRITICAL**, 1 fixable MEDIUM (zlib CVE-2026-85091) |
| Vulnerability gate | Baseline correctly fails; final API + web pass fixable-HIGH/CRITICAL gate; missing report fails |

The five SQLite skips are deliberately PostgreSQL-only: effective database privilege
checks (2), advisory-lock migration safety (1) and native pgvector behavior/scope (2).
Office, OCR, footer geometry and security assertions ran; no failure was suppressed
or assertion weakened. The historical PDF serialization-order failure is resolved in
the baseline integration history and passes unchanged in these suites.

Some initial parallel builds exhausted this workspace's 32 GiB VFS filesystem,
interrupting a PostgreSQL run. Scoped cleanup of this task's build cache and sequential
builds restored space. The table quotes completed reruns, not aborted results.
The production smoke used throwaway PostgreSQL, a generated owner token and a trusted
local test certificate. Docker VFS mounts did not report a separate device, so the test
explicitly verified its named-volume attachment and used the supported sentinel.
This proves the local restart path, not Render disk durability or Supabase connectivity.

## Evidence and reproduction

Workspace evidence is under /workspace/security-evidence (outside git):
sqlite-final.log/xml, postgres-final.log/xml, web-unit.log, e2e.log,
production-native-tests.log, production-runtime-smoke.log, runtime-smoke.py,
limited-role-migrations.log, k3-final.log,
pip-audit.json, pnpm-audit-production.json, pnpm-audit-all.json, gitleaks.json/log,
api-baseline.trivy.json, api-final.trivy.json, web-final.trivy.json and build logs.
The committed [per-finding report](security/private-beta-vulnerabilities.json) records
all 80 remaining HIGH/CRITICAL package findings, versions, reachability, mitigations,
image IDs and scanner database timestamp. Future Security CI retains full raw JSON
as downloadable artifacts; a future run is not claimed to have happened already.
A separate untracked-directory scan matched the existing synthetic token fixture,
its bytecode and generated Next.js internal build keys. These are excluded from git;
no extra ignore/suppression was added. The full-history repository scan is clean.

Representative commands (developer/CI reproduction, not a phone-owner requirement):

    cd apps/api
    uv sync --frozen
    uv run ruff check src tests migrations ../../scripts
    uv run ruff format --check src tests migrations ../../scripts
    uv run mypy
    EZO_REQUIRE_OFFICE=1 EZO_REQUIRE_TESSERACT=1 uv run pytest -q -rs --junitxml=reports/sqlite.xml
    EZO_TEST_DATABASE_URL=postgresql://ezo:ezo@localhost:5432/ezo_test EZO_REQUIRE_OFFICE=1 EZO_REQUIRE_TESSERACT=1 uv run pytest -q -rs --junitxml=reports/postgres.xml
    uv run alembic upgrade head
    uv run alembic check
    cd ../..
    pnpm lint
    pnpm typecheck
    pnpm test
    pnpm test:e2e
    docker build -t ezo-api:review apps/api
    docker build -t ezo-web:review -f apps/web/Dockerfile .
    docker build --target office-tests -t ezo-api-office:review apps/api
    docker run --rm --user 10001 -e EZO_REQUIRE_OFFICE=1 -e EZO_REQUIRE_TESSERACT=1 -v "$PWD/apps/api/tests:/app/tests:ro" --entrypoint python ezo-api-office:review -m pytest -q -p no:cacheprovider tests/unit/test_office_convert.py tests/unit/test_office_safety.py tests/unit/test_process_limits.py tests/unit/test_ocr.py tests/integration/test_office_pdf.py
    gitleaks detect --source . --redact --report-format json --report-path /tmp/gitleaks.json
    python3 scripts/container_vulnerability_gate.py reports/security/api.trivy.json reports/security/web.trivy.json

Database commands must use an isolated test database. Native tools and all five language
packs are required. This cloud environment uses read-only build CA secrets; it never
turns off TLS/package checksums. Trivy 0.76.0 uses its current official GHCR database
because the default mirror is denied by environment policy. No network block was bypassed.

## Hosted GitHub evidence and limits

- Default/integration branch: claude/gifted-goodall-bpf01s, fetched HEAD 422beab.
- Baseline public PR page: 0 open PRs; K3 and earlier deployment/review changes are merged.
- [CI #84](https://github.com/UmidjanDeveloper/EZO/actions/runs/39233572032) and
  [Security #12](https://github.com/UmidjanDeveloper/EZO/actions/runs/39233572057)
  show successful baseline jobs on public GitHub pages. These do not validate this new branch.
- Public branch/rules pages show the default branch is unprotected. The enabled Status
  ruleset has no branch include target and no required PR/check rules. Settings were unchanged.
- api.github.com is denied by the managed environment network policy. Git transport works;
  an injected credential exists. This is not an absent-token diagnosis. API permission
  inspection/PR creation and hosted final-commit conclusions require permitted API access.
  The owner can apply the existing network draft without sharing a new token in chat.

## Release readiness checklist

| State | Status / next evidence |
| --- | --- |
| Code and local regression checks | Complete for the inspected boundaries; residual native risk remains |
| CI configuration | Prepared, immutable action pins and complete vulnerability artifacts; new hosted run must be inspected |
| Infrastructure | Not configured/validated against actual Supabase, Render and Vercel |
| Actually deployed | **No** |
| Independent Claude review | Owner must review final diff and native HIGH/CRITICAL risk |
| GitHub protection | Owner must activate a targeted PR/required-check ruleset |
| License / visibility | Owner decision; no project LICENSE or visibility mutation |
| Cost / release commit | Owner approval needed before provisioning/deploying |
| Real-host acceptance | TLS/session/app role/vector, mounted disk, correct secrets/CORS, live AI/semantic calls and restart durability pending |
| Backups | Matched database/files off-host backup and isolated restore drill pending |

Verdict: **READY AFTER SPECIFIC FIXES**. Complete native-risk review/mitigation decisions,
effective branch protection, hosted final-commit checks and approved infrastructure
acceptance before calling it deployment-ready. Follow the
[phone guide](MOBILE_PRIVATE_BETA_LAUNCH.md) and
[operations runbook](PRIVATE_BETA_DEPLOYMENT.md); remaining risks are in the
[risk register](PRIVATE_BETA_SECURITY_RISK_REGISTER.md).
