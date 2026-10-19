# P0 final hardening and P1 foundation assessment

Date: 2026-10-19. Base: c09e94ce9dc29b2e2a9ec467bbaee3c4d902d9b1.
Branch: fix/p0-final-hardening-p1-readiness.
Verdict: **P0 BLOCKED — specific blockers remain.**

Confirmed capture, cleanup, deadline and citation defects are fixed and locally
verified. Unfixed native-library risk, incomplete hostile-parser isolation and
effective owner-controlled GitHub protection remain unresolved. Green CI is not
evidence that these blockers disappeared. This mission performs no deployment,
provisioning, paid API usage, automatic merge or repository setting change.

## Verified repository and hosted baseline

- Actual default/integration: claude/gifted-goodall-bpf01s; fetched HEAD matches the
  base above. [PR #8](https://github.com/UmidjanDeveloper/EZO/pull/8) is merged into it.
- Public pull dashboard showed **0 open / 8 closed PRs** at audit time. Existing feature
  branches were not overwritten; the work started from the verified integration.
- [CI #86](https://github.com/UmidjanDeveloper/EZO/actions/runs/39271487039) and
  [Security #14](https://github.com/UmidjanDeveloper/EZO/actions/runs/39271487025)
  both succeeded on c09e94c. They verify the baseline, not this new branch.
- Public branches/rules pages confirm no effective protection on the integration
  branch. Status ruleset 25371907 has no included branch and no PR/check requirement.
- Git transport works. GitHub API permission inspection returns Forbidden because
  api.github.com is outside the enforced managed network policy. Admin permissions
  and final-branch hosted checks must not be inferred from that error.
- CI and Security push triggers explicitly include this isolated P0 branch, so its
  final commit can be checked even while PR API creation is unavailable. No deployment
  workflow or external hosting trigger was introduced.

## Concise P0 gaps: verified defects versus risks

| Priority | Finding | Evidence / affected boundary | Result |
| --- | --- | --- | --- |
| HIGH, verified defect | OCR/Office capture could consume unbounded parent RAM before output validation | baseline tesseract.py::_run used capture_output; OfficeConverter.to_pdf_sync used communicate; stdout/stderr flood fixtures failed | Fixed by process_limits.py::run_native, lines 41–119; anonymous files, hard child file limits, bounded reads and diagnostic budgets |
| HIGH, verified defect | OCR timeout killed only the direct process; descendants could survive or hold inherited pipes | real sleeping-child regression, including a parent that exits normally | Fixed: shared process-group cleanup on timeout, failure and success; direct leader reaped |
| MEDIUM, verified defect | Native lock wait was outside the execution deadline | held-lock fixture returned after its requested timeout on baseline | Fixed: one deadline includes queue acquisition and native execution |
| MEDIUM, verified defect | K2 mixed pages/sections and overlap could receive the following location's citation label | two tiny sections produced one chunk labelled with the second heading; two negative cases failed | Fixed in ingestion/chunking.py, lines 89–115: location boundaries flush; overlap stays within the same page/heading |
| BLOCKER, potential runtime risk | libxml2 CRITICAL plus relevant HIGH findings remain unpatched in supported runtime packages | current actual-image Trivy report, ldd system linkage, fresh apt candidate inspection | Open; no exploit demonstration or zero-risk claim |
| HIGH, potential risk | API-process PDF/Pillow/lxml parsing lacks per-file killable CPU/RSS/filesystem isolation | ingestion/service.py::_run_pipeline uses asyncio.to_thread; PDF/image parsing stays in API; lxml bundles native XML | Open; native child limits do not protect these API-thread parsers |
| BLOCKER, confirmed owner setting | No effective PR/review/CI gate on integration branch | public branch and ruleset data, independently rechecked | Exact owner checklist prepared; no settings changed |
| LOW, verified documentation drift | Roadmap claimed images/scans were unread and history implied tag-pinned Actions | implemented OCR; immutable uses references in workflows | Current claims corrected; dated results retained as history |

No arbitrary-command API, cross-owner data leak or new K3 execution path was reproduced.
That is a scoped inspection/test conclusion, not a universal security guarantee.

### Native controls after the fix

OCR captures at most its 8 MiB per-stream read budget; Office diagnostics have a
64 KiB per-stream budget. Anonymous regular files avoid pipe buffering in API RAM.
Linux RLIMIT_FSIZE bounds each child-written file (8 MiB OCR; 200 MiB Office).
The smaller Office diagnostic budget is polled; a fast write can overshoot it on disk
up to the hard per-file limit before the next poll. It is never read wholesale into RAM.

Existing minimal environments, no shell, server-selected binaries, secure per-conversion
temporary directories, archive/relationship validation, CPU limits, zero core dumps,
4 GiB virtual-address limit and denied new IPv4/IPv6 sockets are preserved.
Queue and execution now share a deadline; process-group cleanup also runs on normal exit.

Limits are per process/file, not aggregate RSS/CPU/pid or total temporary-disk quotas.
Same-UID filesystem access and deliberate process-group escape are not contained by
these controls. API thread parsers remain outside the child filter. A blocked network
socket is not a filesystem sandbox. No K4 generated-code executor was introduced.

### Citation compatibility

Freshly ingested/reindexed chunks no longer carry another page/heading's text under
the current locator. Within-location overlap and size limits remain tested. The existing
overlap fixture was made longer to retain its overlap assertion within a page, and
a separate assertion rejects overlap at the page transition; assertions were not relaxed.

Existing persisted chunks are not automatically rewritten. An older populated local
database needs an explicit owner reindex before relying on repaired location metadata.
Reindex can have provider costs when live embeddings are configured; no such calls,
automatic backfill or old-owner-data mutation happened in this mission.

## Current container vulnerability reproduction

Trivy 0.76.0, official checksum-verified binary; database freshly downloaded from the
official GHCR repository at 16:03 UTC, with upstream UpdatedAt 2026-10-19 13:35:30 UTC.
No ignore, severity, checksum, package-signature or TLS threshold was weakened.
Pinned supported Python/Node base digests still match the current official tags.

| Actual image | HIGH | CRITICAL | Fixable HIGH/CRITICAL |
| --- | ---: | ---: | ---: |
| Integration API baseline | 79 | 1 | 0 |
| Final API | 79 | 1 | 0 |
| Final web | 0 | 0 | 0 |

This iteration closes **zero package CVEs**; process containment fixes must not be
presented as package patches. There are 80 API package findings across 29 advisory IDs.
All versions, advisories, assessments and mitigations are retained in
[the machine-readable report](security/p0-vulnerabilities.json), with actual image IDs.
Full unfiltered scan JSON is retained locally and by the Security workflow artifacts.

### libxml2 and relevant HIGH findings

- System libxml2: 2.12.7+dfsg+really2.9.14-2.1+deb13u3. Fresh signed apt indexes offer
  exactly that candidate. LibreOffice libmergedlo links this system library.
- CRITICAL CVE-2026-6653 describes xmlParseInternalSubset UAF/DoS in the affected
  upstream range. OOXML/embedded XML can reach native parsers; exact trigger/flags
  in LibreOffice have not been demonstrated. Defused .rels parsing does not cover
  every XML part consumed by LibreOffice. It remains a blocker for an unqualified
  P0-complete claim.
- lxml separately reports runtime libxml2 2.14.6; current PyPI lxml is 6.1.3.
  The HIGH CVE-2026-86138/86139/86140/86142/86143/86144 descriptions cover libxml2
  before 2.15.4. This is additional potential in-process exposure, not a fabricated
  extra Trivy count. A clean pip-audit does not assess all bundled native code.
- Tesseract HIGH advisories concern crafted .traineddata/model initialization.
  Requests select validated installed language IDs, not a model path. All five
  packaged models are non-writable by UID 10001. No request-to-model replacement
  path was found. CVE-2026-73066 has an upstream 5.5.3 fix, but Debian's candidate
  remains 5.5.0-1+b1 and the other model advisories have no fixed release in their
  descriptions. Models/package supply-chain compromise remains a risk.
- TIFF image-decoder reachability through embedded Office assets is possible.
  The specific CVE-2026-52490 tiffcrop command path is not present: no tiffcrop binary.
  Do not generalize that to every libtiff issue.
- No curl CLI or libxml2 Python SAX binding is installed. EZO uses httpx/SafeFetcher,
  not schemeless SFTP curl commands or Negotiate service connection reuse. These
  advisory-specific paths differ from a claim that all installed libraries are safe.

The web image retains one fixable MEDIUM: zlib 1.3.2-r0, CVE-2026-85091, fixed in
1.3.2-r1. The official Alpine mirror is policy-denied (dl-cdn.alpinelinux.org), and
the current Node base digest is unchanged. No speculative Dockerfile change, disabled
verification or alternate-mirror workaround was committed. Follow up with a signed
supported package/base update and another image/browser verification.

The full Node development audit has one HIGH, braces 3.0.3 (CVE-2026-93687), without
a published patched version in its advisory. It is an ESLint dependency, absent from
the production audit/image. Keep build/lint jobs free of production secrets and track
the upstream fix; an informational development audit is not a clean audit.

## Database, access and agent safety verification

Existing edge guard authenticates before request body consumption and rejects declared/
streamed oversized bodies. Owner-keyed limits, separate failed-auth budget and health
exemption are preserved. Negative tests cover private downloads, storage traversal,
other-owner/project/library/document access and native pgvector scope.

Migrations 0014/0015 revoke direct and PUBLIC/column grants; production readiness checks
effective table/column privileges. The full real-PostgreSQL suite includes PUBLIC table
and column grant failures. Fresh isolated migration upgrade/check and 0015 down/up/check
also pass. No new schema migration was needed for this change.

K1 source reading retains SSRF/robots/budgets/provenance and treats content as data.
K2 library/owner scope, source version/deletion behavior and empty-scope refusal pass.
K3 registry awareness, confidence/evidence labels, license/security cache invalidation
and busy-source behavior pass. Its final negative test forbids process/network calls
and Path text/byte writes, requires nonempty proposal-only output and an unchanged
tool registry. Source-derived text cannot grant code installation, repository writes,
secret access, push or deployment authority. No live model semantic-injection immunity
is claimed; provider behavior was tested with controlled fixtures.

## Exact local validation

| Check | Result |
| --- | --- |
| Ruff lint / format | Passed; 390 files |
| Mypy | Passed; 269 source files |
| Backend SQLite, final code | 793 collected: **788 passed, 0 failed, 5 skipped** |
| Backend PostgreSQL 16 + pgvector | **793 passed, 0 failed, 0 skipped** |
| Native regression before/after | **6 failed before, 6 passed after**; combined launcher test target 8 passed |
| K2 location before/after | **2 failed before**, final chunk/knowledge/learning target **29 passed** |
| Final K3 boundary target | **5 passed**, including blocked process/network/filesystem writes |
| JavaScript | **65 passed**, 0 failed: 55 web + 10 shared |
| Playwright desktop + mobile, final code | **31 passed**, 0 failed, 0 skipped |
| API/web production Docker builds | Passed; image IDs in machine-readable report |
| Image-native OCR/Office/security, UID 10001 | **34 passed**, 0 failed, 0 skipped |
| Alembic fresh upgrade/check, 0015 down/up/check | Passed; no new upgrade operations |
| API production smoke | Passed: local verify-full PostgreSQL TLS, migrations 0015, owner 401/200, CORS, hidden docs, UID 10001, PID 1 Uvicorn |
| File persistence smoke | Passed: API removed/recreated; same DB/named volume; upload survives and reindexes in offline keyword mode |
| Web production smoke | Passed: HTTP 200, nonce CSP, runtime origin-only no-store config |
| Production dependency audits | Python 0 known; Node 0 known |
| Full development Node audit | 1 HIGH retained, explained above |
| Full-history secret scan | 0 leaks; final commit range scanned before push |
| Trivy gate | Passed fixable-HIGH/CRITICAL gate; all unfixed findings retained |
| Compose / workflow validation | Optional voice Compose config parses; workflow shell/YAML and immutable pins checked |

SQLite skips: effective PostgreSQL grants (2), PostgreSQL migration lock (1), native
pgvector tests (2). Native tests ran; no Office/OCR skips or weakened assertions.
No real AI call was made; semantic quality and real external service connectivity
are not verified. Production smoke used local throwaway resources only.

Workspace evidence: /workspace/p0-evidence, including before/after logs, final XML,
builds, full Trivy JSON, DB timestamp, apt candidates, runtime library/model probes,
GitHub public pages and smoke script/logs. Scoped removal of this task's unused build
cache controlled VFS disk growth; no global Docker prune or unrelated image removal.

## Remaining gates and P1 handoff

1. Obtain a supported patch or independently reviewed effective containment for
   native/in-process parser risk. Do not relabel unpatched code as safe from test counts.
   Treat this as a separate remaining P0 security change, not a reason to start broad
   Student work. The later P1 worker must reuse and preserve that containment contract.
2. Owner applies/verifies targeted PR/review plus all seven CI/Security requirements:
   [exact phone/browser checklist](GITHUB_P0_PROTECTION.md).
3. Inspect hosted checks for this new final commit and have Claude review the final
   PR read-only. Policy-blocked API access is stated explicitly in the delivery report.
4. P1 is a plan, not implemented features:
   [small DOCX reading milestone and subsequent Student plan](P1_EZO_STUDENT_V1_PLAN.md).

No production infrastructure, API key, live service, merge or deployment was created
or triggered. Existing experimental features remain experimental.
