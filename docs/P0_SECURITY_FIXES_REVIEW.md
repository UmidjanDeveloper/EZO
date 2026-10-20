# P0 D2–D7 security fixes: independent review handoff

2026-10-20. Base: `bf4eb7dabc3dc8fe9669aa48e34c6b2f3864d7e6` (merged PR #9).
Branch: `fix/p0-parser-process-final`, targeting `claude/gifted-goodall-bpf01s`.
**Verdict: BLOCKED. D6 remains unresolved. Do not merge or deploy this branch.**

This is a focused follow-up to Claude's read-only audit, not a P1 implementation.
Earlier P0 reports retain their historical findings; current branch protection is
now enabled. No GitHub ruleset, deployment, paid provider, production secret,
dependency declaration, lockfile or database schema was changed here.

## Confirmed findings and changes

### D2: bound OOXML before materializing libraries

Existing upload validation limited the complete ZIP to 200 MiB expanded and 5,000
members. That still admitted highly compressed, expensive XML into python-docx's
in-process tree builder and openpyxl's shared-string/workbook loader. DOCX had no
paragraph limit. XLSX's 20,000-row output loop did not bound initial XML parsing or
sparse dimensions/columns.

A common preflight now runs at both ingestion parser entry points, including direct
parser calls and reindexing. It checks all XML and relationship members **before**
calling python-docx/openpyxl:

- 8 MiB per XML member; 32 MiB total XML; existing 200 MiB expanded/5,000-part bounds.
- Duplicate part names rejected; actual XML reads bounded, ZIP CRC errors rejected.
- Streaming defusedxml inspection rejects DTDs/entities/external entities. Completed
  nodes are detached; depth is at most 64, total elements 100,000, paragraphs 20,000,
  sheets 64. These counts apply across the package, not independently per member.
- XLSX dimensions and cell references cannot expand beyond 256 columns/20,000 rows.
  Word table spans cannot exceed 256 or accumulate more than 100,000 logical spans.
- Clear `ParseError` messages and codes (`too_large`, `too_complex`, `corrupt`). The
  existing ingestion response uses `status=failed` and its safe error message;
  `ParseError.code` is available to parser callers, not a new response-schema field.

Accepted documents use the existing parsers and section/citation logic unchanged.
Large documents beyond these deliberate limits now fail rather than truncate their
XML silently. Normal headings, tables, sheet citations and cross-owner tests pass.

**Limit:** preflight and downstream libraries still run in the API process (in its
existing background thread). Their input/tree work is bounded, but not protected by
a killable per-document RSS/CPU sandbox. A preflight is not parser exploit isolation.

### D3: a real PID-1 reaper

The production image previously started the entrypoint/Uvicorn as PID 1. Killing a
native process group and waiting for its leader does not reap orphan descendants.
The image now installs Debian's minimal `tini` and uses
`ENTRYPOINT ["/usr/bin/tini", "--"]`. The existing migration checks and shell `exec
uvicorn` remain intact. Tini reaps adopted orphans and forwards termination to the
application. It does not kill live descendants that intentionally escape containment.

The production-image regression requires UID 10001 and actual `tini` at PID 1,
runs **12 real DOCX/XLSX conversions plus 6 intentionally orphaned native child
lifecycles**, and requires stable zero zombies after each iteration. It failed on
the old image's missing init and passes with the production entrypoint. A local
SIGTERM probe exited 0. The API smoke also verifies graceful Uvicorn shutdown;
Uvicorn may exit 143 after restoring/re-raising SIGTERM, which is distinct from an
unclean SIGKILL/137 timeout.

### D5: restore signals and fail closed at file boundaries

Python starts with SIGPIPE/SIGXFSZ ignored. `execv` preserves ignored dispositions,
so the native launcher must explicitly restore their defaults (also SIGXFZ where
available). It now does so immediately before exec, after limits/network policy.

Captured stdout/stderr reaching either their capture budget or RLIMIT_FSIZE are
rejected even if the binary returns zero. Checks also run after process-group
cleanup to cover descendant writes at leader exit. A converted PDF exactly at the
file boundary is rejected before being opened or returned. This intentionally
rejects an exact-boundary legitimate output because successful completeness cannot
be established there. Existing output/time/network limits are retained.

### D6: attempted smaller memory limit rejected due to a real regression

**Not fixed.** The fixed **4 GiB RLIMIT_AS remains in the shipped code**. An attempted
configurable 1 GiB default, range validation, cgroup-budget cap and enforcement tests
were implemented and then removed after a normal existing Excel fixture regressed.
No passing assertion was removed from the existing suite to accommodate it.

Measured local host LibreOffice behavior, using the unchanged existing
`report_xlsx()` fixture (two sheets and formulas), with only RLIMIT_AS varied:

| Virtual address ceiling | Result |
| --- | --- |
| 1,024 MiB | conversion fails: Unspecified Application Error |
| 1,536 MiB | same failure |
| 2,048 MiB | same failure |
| 3,072 MiB | same failure |
| 4,096 MiB | succeeds, 2 pages |

These are virtual-address compatibility observations, not measured RSS and not
proof that every production-image conversion needs 4 GiB. A smaller default plus
"half the container memory" cap cannot be claimed safe and compatible from this
evidence. Configuring a hidden higher value only for CI would conceal the regression
and was not done. The prototype and its temporary configuration tests are not part
of this diff. D6 needs a reviewed image-specific virtual/RSS sizing decision and
aggregate container/worker enforcement; the owner has not waived it.

## Regression and verification evidence

**Local, final retained code:**

| Check | Passed | Failed | Skipped |
| --- | ---: | ---: | ---: |
| API SQLite (806 collected) | 801 | 0 | 5 |
| API PostgreSQL 16 + pgvector (806 collected) | 806 | 0 | 0 |
| Focused parser/native/citation-preserving parser tests | 30 | 0 | 0 |
| Production-image OCR/Office/native/parser tests | 47 | 0 | 0 |
| Web + shared unit tests | 65 | 0 | 0 |

SQLite skips are PostgreSQL privilege checks (2), migration locking (1), pgvector
operator tests (2). No OCR/Office test was skipped in either final full API run.
The 30/47 focused cases overlap the full suite; do not add their totals together.

There are **13 new regression cases**: 8 OOXML preflight and 5 file-boundary/signal
cases, plus the standalone container lifecycle regression. Six original new negative
cases failed before fixes; the rest extend complexity/boundary coverage. The first
full prototype run had **796 passed, 12 failed, 5 skipped (813 collected)**: ten OCR
failures came from omitting the prepared Uzbek/Russian TESSDATA_PREFIX; two Excel
failures reproduced the memory regression. After selecting the existing verified
language directory and reverting D6, final full suites above pass. Initial Docker
test-target construction also exhausted the managed VFS disk; unused task-owned
images/cache were cleaned, and the final production image built successfully.

- Ruff lint and formatting: pass; mypy: 270 source files pass.
- Frontend lint/typecheck: pass. The frontend was not changed.
- API production build: pass. Final image:
  `sha256:57f2cc975868d74d32d0dac392e4cad943d94826c162ed79c444d6236935324e`.
- Image-native 47 cases use that exact production image, UID 10001 and its own
  native/runtime libraries; only pytest tooling/tests are mounted read-only.
  Production ships no pytest/package installer. The failed office-tests build is
  not represented as a passing build.
- PostgreSQL migration upgrade/check: no schema drift; no new migration.
- Full-history gitleaks: no leaks; runtime pip-audit and production pnpm audit:
  zero known findings. Existing suppressions/thresholds were not changed.
- Desktop/mobile Playwright and web Docker rebuild were not rerun locally in this
  narrowly scoped iteration; they remain enabled in the full hosted CI workflow.
- Hosted checks are **separate** from these local counts. The final delivery report
  records exact SHA, run URLs and observed outcomes after the push; this document
  does not infer hosted success from local tests.

### Actual production-image XML libraries and scanner

The image imports **lxml 6.1.3**, compiled and runtime **libxml2 2.14.6**. Separately,
Debian's system **libxml2 2.12.7+dfsg+really2.9.14-2.1+deb13u3** is linked by
LibreOffice's `libmergedlo.so`. They are different copies. Tini is **0.19.0-3+b8**.

Trivy 0.76.0 was rerun on the final image with its current valid official database
(UpdatedAt 2026-10-19T13:35:30.519058742Z; NextUpdate
2026-10-20T13:35:30.519058502Z). The official refresh was requested; the not-yet-expired
cache remained valid. **79 HIGH / 1 CRITICAL**, zero fixable HIGH/CRITICAL; unchanged
from the previous report. The existing gate passes, while the risk remains.
**CVE-2026-6653 in system libxml2 remains unpatched.** Existing bundled-libxml2
advisory applicability also remains a risk, not erased by a clean pip audit.
No package CVE is claimed fixed here. Full findings remain in the scan artifact;
previous per-advisory assessments are in `docs/security/p0-vulnerabilities.json`.

## D4 / D7: required architectural work for P1.2, not implemented here

The native filter denies new INET sockets, but does not deny `setsid`. A process
that creates a new session can evade `killpg`; tini only reaps it once it exits.
The OCR async API delegates to a thread, so cancelling the coroutine cannot stop
that thread's native work. OCR orientation/deskew/page passes each receive fresh
subprocess timeouts; there is no single document-wide execution budget.

P1.2's approved design must include, before exposing long-running hostile workloads:

1. A separate, unprivileged parser executor without API/DB/provider secrets. Read-only
   input/output channels, private temporary filesystem, no external network or host
   filesystem access. Explicit aggregate RSS, swap, CPU, PID and total scratch quotas
   enforced by the executor's container/cgroup, independently of RLIMIT_AS.
2. Membership-based termination of **all** job processes (including new sessions),
   e.g. per-job cgroup kill; a process-group-only solution is insufficient. Verify
   orphan reaping and cleanup at success, timeout, crash, cancellation and shutdown.
3. One monotonic document deadline covering queue wait, validation, PDF rendering,
   orientation, deskew, every OCR attempt/page, serialization and result publication.
   Pass remaining time to nested operations; do not reset the budget per page.
4. Explicit cancellation state propagated to the executor, prompt group/cgroup
   termination, reaping and scratch cleanup. Do not rely on cancelling `to_thread`.
5. Durable PostgreSQL leased jobs with fenced, idempotent publication. A cancelled,
   expired or replaced worker must not publish late chunks/artifacts. Bounded partial
   results need explicit completeness/citation state, never silent truncation.
6. Adversarial tests for setsid/double-fork survival, cancellation during each phase,
   repeated timeout/zombie accumulation, aggregate memory exhaustion, recovery and
   cross-user/workspace file/data separation.

These are design/acceptance requirements only. No queue, sandbox, executor, Student
feature or K4–K7 capability was implemented. P0-required containment is not waived
by putting a future implementation under the P1.2 label.

## GitHub handoff and exact changed files

Read-only public rules data confirms active ruleset 25371907 targets the integration
branch, blocks deletion/force pushes, requires PRs, all seven existing CI/Security
contexts and up-to-date status checks, and shows no bypass actors. Independent
approval remains **0 required**; code-owner and last-push approval are not required.
No setting was modified. The legacy `protectedByBranchProtections=false` field is
not proof that this active ruleset is ineffective.

Git transport works. The managed runtime still denies api.github.com; the saved
onboarding draft already includes that host but has not been applied to this running
instance. PR creation is attempted after pushing, with its exact outcome in the
final report. The owner must apply the saved network configuration to unblock the
supported GitHub API route; no policy bypass or new secret request is used.

Changed files (relative to repository root):

- `apps/api/src/ezo_api/documents/ooxml_limits.py`: common bounded preflight.
- `apps/api/src/ezo_api/knowledge/parsers/base.py`: safe parse error codes.
- `apps/api/src/ezo_api/knowledge/parsers/office.py`: guard both ingestion parsers.
- `apps/api/tests/unit/test_office_parse_limits.py`: compressed/complex XML fixtures.
- `apps/api/Dockerfile`: minimal init and entrypoint.
- `apps/api/src/ezo_api/documents/process_limits.py`: signals/capture boundaries.
- `apps/api/src/ezo_api/documents/office_convert.py`: reject exact-limit PDF.
- `apps/api/tests/unit/test_native_execution.py`: five boundary/signal regressions.
- `apps/api/tests/container_native_reaping.py`: real container lifecycle regression.
- `.github/workflows/ci.yml`: run lifecycle regression and image parser cases; narrow
  push trigger for this feature branch so hosted validation can run without API PR access.
- `.github/workflows/security.yml`: same narrow push trigger; gates unchanged.
- `docs/P0_SECURITY_FIXES_REVIEW.md`: this report and D6/D4/D7 remaining work.

**Do not merge or deploy. D6 and native-library risks require independent review;
PR creation also depends on restoring the supported API route.**
