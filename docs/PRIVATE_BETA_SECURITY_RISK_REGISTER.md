# Private beta security risk register

Assessment baseline: 422beabca8d9d6f96118cd5adc8b0cc2550a781e.
Working branch: fix/final-private-beta-hardening. Date: 2026-10-19.
Scope: one owner, Vercel UI, one Render API/disk, Supabase PostgreSQL. No live
resources, production credentials, repository setting changes or deployments were used.

## Previous findings revalidated

| Finding | Current assessment | Evidence and practical limit |
| --- | --- | --- |
| H1 unauthenticated body consumption | Fixed and verified | security/edge.py authenticates before receive(); unit/test_edge.py and integration/test_deployment.py cover declared/chunked oversize, zero body reads on 401, owner access and preflight |
| H2 rate limits/proxies | Fixed and verified | api/deps.py uses an authenticated owner key, not spoofable forwarding headers; attacker failures have a separate global budget; health has no rate limit; owner/daily-budget regressions pass |
| H3 learning intent hijacking | Fixed and verified | unit/test_learning_routing.py plus chat/IELTS routing suites; active language sessions and ordinary learning requests remain separated |
| H4 injected source instructions | Fixed and verified at the data boundary | knowledge/retrieval/citations.py escapes source tags; K3 reports are untrusted source blocks; analyzer tests deny execution/network and check proposal-only output. This does not prove a live model will resist every semantic injection |
| M1 production defaults | Fixed and verified | deployment.py rejects unsafe auth, TLS, CORS/debug/private-network settings and hosting markers with a forgotten production mode |
| M2 durable storage | Requires live deployment validation | local production remove/recreate/reindex with retained volume passed; mounted-disk/sentinel preflight exists. A sentinel is owner attestation, not proof of provider durability, encryption or backups |
| M3 database exposure | Fixed and verified for effective table/column privileges | prior direct-grant check missed PUBLIC/inherited and column grants. New readiness query checks effective privileges; migration 0015 revokes PUBLIC and column grants. Real PostgreSQL negative tests pass |
| M4 pgvector | Fixed and verified locally; Supabase still needs live checks | 0014 repairs missing table; native pgvector owner/document/project filters are tested. Owner must enable vector and verify hosted TLS/session access |
| M5 CSP | Fixed and verified | nonce proxy/layout and production browser tests cover pages with no CSP violations, including mobile. Verify real Vercel settings after deployment |
| M6–M8 K3 evidence, licensing, scope | Fixed and verified for inspected boundaries | bounded SQL document reads, registry names, inferred confidence, retained security/license flags and ownership tests were already present. Added cache invalidation for registry/license/security metadata, busy-read rejection, malformed-cache fallback and actual pgvector scope regression |
| M9 LibreOffice footer test | Fixed and verified | integration history replaced serialization-order assumption with geometric footer checks; existing assertion remains intact and passes on host and image-native Office tests |
| M10 branch protection | Not fixed; owner action required | public GitHub /branches says protectedByBranchProtections=false. Existing enabled Status ruleset has no branch include target and only deletion/non-fast-forward rules; it has no required PR/check rules. Settings were not changed |

Source paths in the table are relative to apps/api/src/ezo_api or apps/api/tests.
Executable results and exact counts are in [validation](PRIVATE_BETA_VALIDATION.md).

## New proven defects corrected

1. **HIGH — Office relationship filter bypass / archive expansion.**
   The previous regex skipped single-quoted TargetMode and namespaced Relationship
   elements. A compressed oversized .rels file was read without a pre-decompression
   budget. Six regression cases failed before the fix. office_convert.py now uses
   defusedxml with DTD/entities/external entities disabled, a 1 MiB per-relationship
   part and 8 MiB total budget, and parsed attributes rather than string matches.
   Tests: unit/test_office_safety.py, existing conversion tests. Only synthetic
   non-routable fixture URLs were used; no exploit network request was made.
2. **HIGH — inherited Supabase Data API access missed.**
   information_schema.role_table_grants missed access inherited from PUBLIC and
   column-specific grants. has_table_privilege/has_any_column_privilege now gate
   production startup, including role inheritance. Migration 0015 revokes these grants
   without re-opening them on downgrade. Real PostgreSQL tests cover both grant forms.
3. **MEDIUM — stale K3 analysis/equivalence claims.**
   A cache keyed only to content/analyzer version survived registry, licensing or
   warning changes. An empty registry was also replaced with the default registry.
   Context hashing and an explicit None distinction correct this; cached GET while
   reading now returns 409; damaged cached JSON becomes a miss. No generated tool
   is registered, installed or executed. No K4–K7 work was introduced.
4. **LOW — deletion notice localization.**
   Library deletion always inserted an Uzbek message even for English/Russian UI
   preferences. Three executable language cases now verify the owner preference.

## Container findings: all HIGH/CRITICAL are retained in the report

Scanner: Trivy 0.76.0; official release checksum verified. Its database was downloaded
from the official GHCR repository, updated 2026-10-19 13:35 UTC (not a stale/offline DB).
The pinned Python base digest matches the current supported tag; signed Debian updates
were applied. No checksum, package signature or TLS verification was disabled.

| API production image | HIGH | CRITICAL | Fixable HIGH/CRITICAL |
| --- | ---: | ---: | ---: |
| Baseline actual image | 83 | 1 | 4 |
| Hardened actual image | 79 | 1 | 0 |

The web image has 0 HIGH / 0 CRITICAL and one fixable MEDIUM:
CVE-2026-85091, Alpine zlib 1.3.2-r0, fixed in 1.3.2-r1. Its native runtime
reachability has not been demonstrated. Follow up with a reviewed signed Alpine/base
update and repeat image/browser checks; it does not fail the HIGH/CRITICAL gate.
The production Node audit is clean. The full development audit separately reports
HIGH CVE-2026-93687 / GHSA-vfj7-8cjw-p6xm in braces 3.0.3, with no patched version
in the advisory. pnpm why resolves it only through eslint-config-next → ESLint
plugin → fast-glob → micromatch; it is absent from the scanned runtime image.
Do not run lint/build tooling on attacker-controlled branches with production secrets.
Track the upstream fix; do not use a speculative override or omit the finding.

These are package-vulnerability findings, not unique CVEs. Every remaining finding,
installed/fixed version, severity, vendor status, runtime/reachability assessment,
mitigation and residual risk is in the machine-readable
[per-finding report](security/private-beta-vulnerabilities.json).
Full unfiltered Trivy JSON is retained in the workspace and future CI artifacts.
The four removed findings came from unused build tooling: msgpack, setuptools and
two urllib3 advisories. Runtime now excludes pip/ensurepip, uv/uvx and build caches;
application runtime urllib3 remains at its locked patched version. This is component
removal, not a claim that the unmodified Debian vulnerabilities were patched.

**Remaining CRITICAL:** CVE-2026-6653 in libxml2. The scanner reports affected XML
parsing with no fixed Debian version. Owner-supplied OOXML/embedded content reaches
native document parsers; exploitability of this precise package/code path has not
been demonstrated. Treat it as potentially reachable, not harmless OS metadata.
The 79 HIGH findings include Tesseract, libtiff, libcurl and OS/transitive packages;
direct and uncertain paths are distinguished in the JSON. No blanket non-exploitable
claim or suppression was added.

### Mitigations and their limits

- Authentication occurs before consuming untrusted request bodies; no unrestricted
  public AI or parser endpoint is intended.
- Fixed OCR/Office commands use minimal child environments and no shell. Defused
  relationship parsing rejects linked external data before conversion.
- Native child execution on Linux denies new IPv4/IPv6 sockets with libseccomp and
  no-new-privileges, while retaining local IPC. This is tested before exec, not merely
  a promise that an HTTP client will choose not to connect.
- Native conversions share one lock to avoid overlapping heavy jobs. Limits apply
  to CPU time, existing wall-clock timeout, 4 GiB virtual address space, output file
  size and zero core dumps. The host's container memory limit still matters:
  virtual address space is not resident RAM. The development LibreOffice build used
  about 3.3 GiB RSS on a synthetic workbook, so 1.5/2 GiB address caps broke legitimate
  conversion; those failed trials were corrected without weakening document assertions.
- Production is non-root. Same-UID filesystem/process exposure remains: these guards
  are not a complete sandbox and do not implement the K4 user-code executor.
- Input/archive checks, cleanup, limited pages and output verification remain.
  Native parser crash/OOM and container downtime remain possible. Independent
  in-process Python/PDF parsers are not covered by the native child socket filter.

The selected features are retained; none was silently disabled. If the owner prefers
disabling a native feature pending a distro fix, that requires an explicit decision,
updated UI/docs and regression checks. No such disablement was performed here.

## Workflow and repository controls

- Actions are pinned to immutable, verified upstream commit SHAs; Dependabot retains
  update responsibility. Trivy is pinned by version and image digest.
- All scans emit machine-readable artifacts. Fixable HIGH/CRITICAL findings fail the
  image gate. Scanner/network/report errors fail; no broad || true gate remains.
  Development-only Node audit is explicitly informational and retained as a separate
  artifact. All unfixed findings remain visible; a green gate is not release approval.
- Existing full-history secret scan remains; the sole pre-existing ignored fingerprint
  is the reviewed synthetic redaction test token. No new scan suppression was added.
- Public GitHub pages verified: repository is public; integration HEAD 422beab;
  baseline open PR count 0; K3 is merged in history. Exact required CI check names
  were read from CI #84. API/admin permission inspection and PR creation are blocked
  by the environment's api.github.com policy, not evidence of absent user credentials.
- Repository settings, required checks and visibility were not mutated.
  See the [phone guide](MOBILE_PRIVATE_BETA_LAUNCH.md) for an effective ruleset.

## License decision belongs to the owner

| Direction | Practical effect |
| --- | --- |
| Proprietary + private repository | Restricts access and reuse; suitable initial direction for a single-owner commercial beta. Visibility is separate from copyright license; existing public copies are not recalled |
| Public without project license | Public access is not a permissive open-source license; ordinary GitHub viewing/fork terms still apply |
| MIT | Broad reuse/commercial modification with copyright/license notice; no explicit patent grant comparable to Apache |
| Apache-2.0 | Broad reuse plus explicit patent terms; preserve license/notice obligations |
| BSD-3-Clause / AGPL | BSD is permissive with a non-endorsement condition; AGPL has much stronger source-sharing obligations for network use and needs a deliberate product/legal decision |

Recommendation: decide proprietary/private versus a permissive public license before
external beta invitations. No LICENSE file or visibility change was made. Dependencies
keep their own licenses regardless of this choice; defusedxml is PSF-licensed and the
  native libseccomp library is LGPL-2.1-only, used in the separate native launcher process.

## Owner decisions and release gate

- **Blocker:** fix or explicitly review/accept the remaining potentially reachable
  native CRITICAL/HIGH risk with Claude and appropriate operational containment;
  never describe the current scan as zero-risk.
- Apply an effective integration ruleset requiring PR plus the four verified checks.
  The currently enabled but untargeted ruleset does not supply this protection.
- Choose license/visibility; approve paid hosting and the exact deployment commit.
- Configure real Supabase TLS/extension/roles, Render disk and resource settings,
  Vercel origins/protection, AI budgets and matched backup/restore tests.

No owner decision was inferred from silence. Local code/test readiness, hosted CI,
infrastructure readiness and actual deployment are separate states.
