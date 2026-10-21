# Full-owner beta validation / independent-review handoff

Base `c3303d94c128406dfd286168cd9dd02079c61f1a`;
branch `feat/full-owner-beta-budget`; schema head remains 0018.
Status: **BLOCKED for deployment**, not a claim of production readiness.

## Confirmed findings and minimal changes

- Gemini/OpenAI chat+embedding and OpenAI audio adapters already implemented; retained.
  Added shared process-local model admission bounds and independent voice bounds.
  Neither is a durable multi-process financial ledger; provider spend controls needed.
- ElevenLabs missing: new bounded server-side STT/TTS REST adapter, no new dependency.
  Tests cover exact contract, private headers, immutable HTTPS host/no redirects,
  safe errors, byte/text caps, no unverified Uzbek TTS claim and voice-less STT-only.
  Upstream generated SDK raw clients at `f5d53e09e35717523435cee238ac5cc7f51966fb`
  were inspected; no live API/key/model quality validation occurred.
- Confirmed IELTS fabrication: baseline new regression returned constant pronunciation
  6.0 for text alone. Removed word-count band/criteria scoring in all profiles, made
  schema fields nullable and updated browser rendering and existing expectations.
  Text practice remains; no validated AI band assessor implemented. Existing historical
  scores are not silently rewritten and must not be treated as validated assessments.
- Super Admin had tests but no operator setup command. Added explicit offline
  existing-owner grant/revoke, exact configured email, no public escalation route.
  Tests cover normal403, granted200, product access, no autonomous deployment, revoke403.
- Full profile is existing `full`, not a new permission bypass. New environment example
  preserves product availability while unsupported native operations still fail closed.
- $10 full native operation needs primary + dedicated executor hosts; Oracle capacity,
  current pricing/taxes, backups, real VM benchmarks and missing OCR/Office worker
  integration remain open. No unsafe same-daemon cohosting shortcut was introduced.

## Verification

Raw local evidence: `/workspace/full-owner-evidence/`. Exact-head hosted outcomes
are recorded in final handoff, not inferred from earlier PRs.

| Check | Actual local result |
| --- | --- |
| Full backend SQLite | 1006 passed, 0 failed, 33 skipped |
| Full backend PostgreSQL/pgvector | 1016 passed, 0 failed, 23 skipped |
| Final focused provider/voice/IELTS/owner regressions | 48 passed, 0 failed/skipped |
| Isolated native container regressions, current image | 22 passed, 0 failed/skipped |
| Ruff / formatting / mypy | Passed; 454 Python files, 307 source files checked by mypy |
| Frontend lint / typecheck / unit / production build | Passed; 68 unit tests (58 web, 10 shared) |
| Playwright | Main desktop/mobile suite 38 passed; separate new IELTS browser case 1 passed |
| PostgreSQL migrations | Upgrade head 0018 and Alembic check passed; vector type autogenerate warning retained |
| pip-audit / pnpm production audit | 80 Python packages, 0 advisories; Node 0 advisories |
| Secret scan before final commit | 155 commits, 0 leaks; committed scan recorded in final handoff |
| API Docker | Built `sha256:a3f94a8c53ef921877b0ffbe3282f2036e363c47e21931e5d8b3ea310d3e0570` |
| Web Docker | Locally blocked by signed Alpine APK endpoint 403, exit99; no upgrade/trust bypass |
| Fresh API Trivy | 44 HIGH, 0 CRITICAL, 0 fixable HIGH/CRITICAL; 58 MEDIUM, 61 LOW, 1 UNKNOWN |
| Real 4/8 GB VM benchmarks | BLOCKED: neither VM available; no result fabricated |

SQLite skips comprise 11 PostgreSQL-only cases and 22 separately run native cases.
PostgreSQL skips comprise one SQLite-only case and those same 22 native cases.
Full backend suites collected 1039 cases before two additional stream-cancellation /
trickled-response deadline tests were added; both new cases passed in the final
48-case focused run afterward. No production source changed between these runs.
Hosted suites collect the final test tree; hosted counts are not inferred locally.

Actual image runtime: certifi 2026.10.19, lxml 6.1.3, bundled/compiled libxml2 2.14.6,
OpenSSL 3.5.7. Unpatched advisory details/reachability remain in
[the native dependency register](STUDENT_V1_DEPENDENCY_RISKS.md) and actual
`/workspace/full-owner-evidence/api-trivy.json`; no ignore rules or thresholds changed.

Failed setup attempts remain in raw evidence. Initial SQLite run: 996 passed,
10 failed, 33 skipped; initial PG run: 1003 passed, 10 failed, 3 errors, 23 skipped.
The OCR tests initially saw only system English data; unchanged baseline reproduction
also failed the same 0.9 recall threshold. Pointing TESSDATA_PREFIX to existing
Uzbek/Russian/English packs corrected the test environment. Initial API build also
exhausted workspace disk, affecting PG fixtures. Removed only task-owned build/cache
records and old task images, then reran successfully; no global prune or baseline
user image removal. First browser launch was blocked by read-only uv cache and then
missing Playwright download; proper workspace cache and installed system Chromium
allowed the full suite. First pip-audit attempt similarly needed a writable cache.
These failed attempts are not reported as passing runs.

Initial failure evidence is retained, including the baseline IELTS regression and any
native OCR/environment failures. Thresholds, OCR recall requirements, security gates,
auth, consent and sandbox restrictions are not weakened to make tests green.
No independent reviewer has approved this patch; separate review remains pending.

## Remaining blockers

- No attached 4/8 GB Linux VMs, cloud identity or approved provisioning. Collector
  refused the 32 GiB environment. Complete-stack VM throughput/latency not measured.
- Official VPS/Oracle/GCP/ElevenLabs docs returned proxy403. Present pricing, quotas,
  account eligibility, taxes, capacity and model access are unverified.
- No live Gemini/OpenAI/ElevenLabs calls, quality or invoices; owner having access
  does not mean credentials exist in this runtime (none configured).
- Student isolated protocol handles PDF/DOCX/EPUB text extraction; scanned OCR and
  native Office conversion are not integrated into a safe production worker protocol.
- Existing native dependency advisories, shared-kernel escape risk, localStorage
  token persistence, backup/restore and dedicated-host isolation review remain open.
- Budget counters reset/repeat across restarts/replicas; internal SDK retries,
  image/search and other processes have separate consumption. Not a hard dollar cap.
- No schema rewrite, public launch, credential creation, paid activation, cloud
  provisioning or deployment. Assistant must not merge or auto-merge the PR.
