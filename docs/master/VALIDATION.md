# Master candidate verification

The records below describe the earlier master candidate. For the 23 October
continuation, see the latest section of IMPLEMENTATION_STATUS.md, the owner-supplied
P0–P9 acceptance matrix, and the `ezo-master-completion-evidence` task handoff.
Earlier historical counts and workflow links do not validate the continuation HEAD.

Integration base: **c3303d94c128406dfd286168cd9dd02079c61f1a**.
Preserved PR21 ancestor: **3ec6cf1cfc7e90588f8c3c2a033a255c3ff70c0b**.
Backend source/test commit: **4af75877696bc82584bf3c8986ed2563d00abd2b**. Contract/research commit: **c43727df4e0d176854f84f9d3d46847f5b9de2c0**.
A later confirmed concurrent-delete/review race is fixed in **a2097f98e3e2c596016a1bd795f265b049968ec3**.
The real PostgreSQL study subset passed **12/12** after the fix (the reproducer
failed before it). Full backend reruns and hosted checks for this final source
are in progress at this evidence commit. The table below records completed
pre-race-fix full suites; final current-head JUnit/status is in the attached
`ezo-master-review-evidence` archive and GitHub Actions, not invented in advance.

## Completed local checks — 22 October 2026

| Check | Actual result |
|---|---|
| Full backend SQLite, OCR/Office required | **1038 passed,0 failed,35 skipped** (1073 collected), before the added delete-race case |
| Full backend PostgreSQL/pgvector, OCR/Office required | **1050 passed,0 failed,23 skipped** (1073 collected), before the added delete-race case; concurrent duplicate reviews included |
| New flashcard regression subset | **8 passed,0 failed,0 skipped**; also included in final full suites |
| Ruff / formatting | Passed;465 Python files formatted |
| mypy | Passed;313 source files |
| Frontend lint/types | Passed |
| Frontend unit tests | **68 passed** (58 web +10 shared), no failures |
| Production Next.js build | Passed (`pnpm build:web`) |
| Playwright desktop/mobile | **39 passed,0 failed,0 skipped**; existing browser routes, no new frontend feature coverage claimed |
| Alembic upgrade/check | Revision0019 upgrade and drift check passed on a separate disposable PostgreSQL database; existing unknown-vector autogenerate warning remains |
| Production API Docker | Passed;image **sha256:d59949f51848ea67eb29906de438ec5f6fa7fc4849ce39d45398240565db8d93**,567136529 bytes |
| Bounded API image smoke | Passed:768MiB limit,network-none/read-only,auth401/200,migrated study routes,LlamaIndex import,native binaries absent;193.8MiB one idle sample, **not** a VM/full-stack benchmark |
| Production web Docker locally | **Blocked**: signed Alpine package upgrade denied403, exit99; upgrade/TLS/trust were not bypassed |
| Real native container regressions | **17 passed +5 passed,0 failed,0 skipped** in two idle runs (controller/hostile tests and real Student workers); initial1 passed/21 failed retained below |
| pip-audit locked runtime | **115 distributions,0 known vulnerabilities** |
| pnpm production audit | **0** vulnerabilities; all-dependency audit retains1 HIGH development advisory |
| Trivy0.76.0 API | **44 HIGH,0 CRITICAL,0 fixable HIGH/CRITICAL**,58 MEDIUM,61 LOW,1 UNKNOWN |
| Secret scan |159 commits,0 leaks at c43727d; final evidence commit will be rescanned |

Native/PG skips require their stated runtime; no SQLite claim of SKIP LOCKED or
container isolation. The native suite is separately opt-in. Repeated test subsets
are not added to the full-suite totals as if they were distinct cases.

Trivy DB updated **2026-10-22 01:15:55 UTC**, downloaded07:11:30 UTC. API runtime
actually reports `llama-index-core0.14.25`, `lxml6.1.3`, compiled/runtime libxml2
**2.14.6**. Container's learning.py SHA256 matches workspace:
`ced2605c92a718c77412659f3cb37af346475e2ee18ac93ab1b1052c25a17527`.
[Remaining package IDs/versions](api-high-vulnerabilities.json) and
[reachability limits](SECURITY_REMAINDERS.md) are not suppressed.

## Failures retained and investigated

- Real PostgreSQL concurrent deletion reproducer: **1 failed** before the fix;
  ORM refresh of a deleted row raised500. The fix locks document then card and
  explicitly returns404 for a missing card. Existing version/idempotency fences
  remain. PostgreSQL study subset then passed **12/12**.

- An early synthesis fixture referenced a nonexistent FakeProvider.calls field:
  **8 passed,1 failed**. Fixed the fixture to inspect actual requests/embed_calls.
- First flashcard fixture cited source1 while quoting source2: **29 passed,1 failed,
  1 skipped** in the mixed focused run. Validation correctly rejected it; the fixture
  now cites the actual quote source. No citation check was weakened.
- mypy caught reused loop-variable types after adding flashcards; variable names
  were corrected, with strict typing retained. Source modules now pass.
- Initial PostgreSQL full run: **428 passed,23 skipped,10 errors**, interrupted
  after PostgreSQL logged `No space left on device` during concurrent VFS image
  builds. Only task-owned images/cache were cleaned; baseline/user images preserved.
  Final full PG rerun passed1050/23. This was an environment failure, not hidden.
- First real native run: **1 passed,21 failed**. DOCX container `docker create`
  exceeded the existing15-second control deadline during shared-host disk load,
  leaving a late-created, never-started namespace. Subsequent requests correctly
  refused the reserved slot. Parser execution did not occur. The existing120-second
  stale-created recovery and all isolation/time limits remain unchanged. Idle rerun
  evidence is recorded above; larger images/VFS latency remain a hosting concern.
- An initial root `pnpm build` command did not exist; corrected to the repository's
  `pnpm build:web`. The final production build passed.

## Hosted checks and PR access

Push checks for source/contract headc43727d:

- [CI#154](https://github.com/UmidjanDeveloper/EZO/actions/runs/39739407382): in progress at last recorded observation.
- [Security#81](https://github.com/UmidjanDeveloper/EZO/actions/runs/39739407432): **success**, Python/Node/images jobs completed.

These are timestamped historical observations, not final-head CI claims.
Latest exact-head run states are captured in the final review evidence archive.
Hosted job states are read from public GitHub run pages. Hosted log/artifact API
access is forbidden; no hosted test counts, detailed scan counts or hidden logs are
invented. Local web Docker failure is distinct from the hosted Docker job success.

Branch **feat/master-build-candidate** is pushed. Draft PR creation was attempted
with gh against integration and failed `POST https://api.github.com/graphql:
Forbidden` (403). No callable GitHub connector is available. PR21 remains preserved;
no new PR URL is fabricated. Compare/review candidate:
https://github.com/UmidjanDeveloper/EZO/compare/claude/gifted-goodall-bpf01s...feat/master-build-candidate

Raw JUnit, build/audit logs, source/security research and timestamps are retained in
`/workspace/ezo-master-evidence` and will be archived with the final report. No real
AI calls, cloud services, production credentials, merge or deployment occurred.

## Verdict

**BLOCKED — full master roadmap acceptance is not met.** The source-specific
backend candidate is reviewable; it is not a completed Full EZO OS or a production
readiness declaration. Unfinished capability/runtime/frontend/budget/review gates
are explicit in [ACCEPTANCE_MATRIX.md](ACCEPTANCE_MATRIX.md).
