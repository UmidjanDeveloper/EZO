# Private beta preparation: validation and review record

Prepared from `7a27466ec2e2b721be3bf0ed02f6753e481fd7e1` on
`feat/private-beta-deploy`, targeting `claude/gifted-goodall-bpf01s`.
No live deployment, production credentials or paid resources were used.
See [the architecture and operations runbook](PRIVATE_BETA_DEPLOYMENT.md).

## Results in the cloud workspace

| Check | Result |
| --- | --- |
| Python `ruff check src tests migrations ../../scripts` | Passed |
| Python `ruff format --check src tests migrations ../../scripts` | Passed, 375 files |
| `mypy` | Passed, 266 source files |
| Backend SQLite `pytest -q -rs` | **717 passed, 1 failed, 1 skipped**; skip requires PostgreSQL/pgvector |
| Backend PostgreSQL 16 + pgvector `pytest -q -rs` | **718 passed, 1 failed** |
| New production policy, redaction, owner auth, CORS and health regressions | 23 passed (included in the full suites) |
| PostgreSQL Alembic upgrade through 0013, then `alembic check` | Passed; no schema drift |
| Frontend lint and workspace TypeScript | Passed |
| JavaScript unit tests | 63 passed: 53 web + 10 shared |
| Next.js production build | Passed in browser-test setup and web Docker build |
| Selected Playwright tests | 7 passed: chat, runtime config, settings, uploads/conversion/download, artifact lifecycle |
| API and web Docker image builds | Passed, frozen lockfiles and TLS verification retained |
| Local Compose including optional voice profile | Configuration parsed successfully; voice service was not started |
| Production API container | Verified PostgreSQL TLS (`verify-full` with a locally trusted test certificate), migrations, `PORT=10000`, health 200, owner auth 401/200, hidden docs, real upload |
| Durable files after container removal/recreation | Same upload metadata survived in PostgreSQL; reindex read the file from the retained named volume; keyword chunk remained available |
| Container identity/process | API ran as UID 10001; Uvicorn was PID 1; graceful stop/recreation succeeded |
| Web container | Homepage HTTP 200; `/ezo-config` emitted only the configured public API origin |
| Updated Docker CI smoke commands, executed locally on isolated ports/names | Passed: unsafe production rejected, migration failure rejected, owner auth and retained-volume restart |

PostgreSQL tests were rerun after recovering disk space exhausted by the Docker VFS
build cache. The table reports the completed rerun, not the aborted/resource-failed
runs. Build trust used read-only BuildKit CA secrets; verification was not disabled.
The production smoke used local throwaway PostgreSQL, a local test certificate and a
generated test owner token. It does not prove Supabase or a deployed host is reachable.
Uploads used offline keyword indexing (`partial` with one chunk); live semantic
embeddings and AI providers were not tested.

## Known failing check: release gate remains open

**Resolved 2026-10-19 (commit `ac41368`).** The assertion relied on text serialization
order. It now reads each page's bottom tenth by coordinates and requires exactly `1` and
`2` there (and the letterhead in the header band) — stricter than before, not weaker.
CI runs `test_office_convert.py` and `test_office_pdf.py` inside the built production
API image with `EZO_REQUIRE_OFFICE=1` (job *Docker*, step "Office tests pass with the
image's own LibreOffice version"); it passed in CI run #82. The original record follows.

`apps/api/tests/unit/test_office_convert.py::test_official_letter_keeps_pages_header_footer_table_and_scripts`
fails at line 52. It asserts that serialized PDF text ends with the page number. The
same failure was observed before this task, in both complete database suites, and
when the fixture was converted in the production Docker image (LibreOffice 25.2.3.2).
The page numbers are present at PDF y=39 on both pages, in the footer; text extraction
emits them before body text. The host LibreOffice development build also fails this
ordering assertion. No assertion was modified, skipped or weakened. Independent
review must resolve this test/serialization assumption before declaring all checks
green; the PR must not be represented as release-approved while it remains red.

## Exact changed files

- `.dockerignore`
- `.github/workflows/ci.yml`
- `apps/api/.dockerignore`
- `apps/api/Dockerfile`
- `apps/api/entrypoint.sh`
- `apps/api/src/ezo_api/deployment.py`
- `apps/api/src/ezo_api/main.py`
- `apps/api/src/ezo_api/api/routes/system.py`
- `apps/api/tests/unit/test_deployment.py`
- `apps/api/tests/integration/test_deployment.py`
- `apps/web/Dockerfile`
- `apps/web/vercel.json`
- `apps/web/app/ezo-config/route.ts`
- `apps/web/lib/runtime-config.ts`
- `apps/web/lib/runtime-config.test.ts`
- `tests/e2e/specs/deployment.spec.ts`
- `render.yaml`
- `deploy/private-beta.env.example`
- `docs/PRIVATE_BETA_DEPLOYMENT.md`
- `docs/PRIVATE_BETA_VALIDATION.md`

No dependency declaration/lockfile or Knowledge OS K3, learning, research, IELTS,
presentation, SkillForge or capability-analysis implementation was modified. The
only shared API source overlaps are isolated startup and health changes documented
in the runbook.

## External verification and owner actions

Git fetch works through the supplied proxy. GitHub API access was denied because
`api.github.com` is outside the enforced environment network policy. Its addition
was saved in the environment draft for review. A GitHub PR URL and hosted CI conclusion
must be reported only after creation/inspection succeeds; local checks are not hosted CI.

Before release: resolve/review the remaining failed check; inspect hosted CI; approve
provisioning and the exact release commit; configure Supabase extension, verified TLS,
session connection, backups and disabled public Data API access; attach the Render
disk; set API-only secrets and exact CORS; set Vercel's public API origin and workspace
root; complete the real-host owner-auth, file-restart and restore checks. Hosting cost
estimates, single-instance limits, browser-token risk, interruption behavior and rollback
constraints are in the runbook. No claim of a live deployment is made.
