# EZO canonical backend completion / acceptance record

2026-10-26. **Overall: PARTIAL / BLOCKED, not production-ready.**
Authoritative integration inspected: `e8febe6e92a8cf5a01d98d99f961acdee38c89cc`.
Candidate branch: `feat/final-backend-acceptance`. No merge or deployment authorized.
This consolidates the supplied final backend directive without replacing the owner
roadmap. Earlier mission documents list PRs as open even though the current Git
history merges them. Their test counts are historical, not this candidate's evidence.

## New confirmed security/reliability fixes

- Approved artifact output hashes were not compared with current artifact bytes at
  send time. A regression replaced bytes after review and the baseline sent them.
  Entire batch bytes are now frozen and hash-verified before any external effect.
- Approval consumption previously shared the transaction with Telegram I/O. A test
  simulated a crash after remote acceptance: rollback allowed a repeated decision
  to send again. Consumed authority and dispatch intent now commit **before** I/O.
- Each verified message receipt commits independently. A crash cannot silently
  authorize retransmission. A stale dispatch (>2min) is fenced by task/step locks,
  becomes `delivery_unknown`, and is never automatically retried. A message accepted
  remotely without its receipt reaching SQL remains unknown, not fabricated success.
- Task cancellation and recipient revocation are rechecked between documents while
  task/step/recipient locks serialize each bounded send. Already in-flight messages
  cannot be recalled; cancellation stops the next document. No exactly-once claim:
  Telegram does not provide a distributed transaction/idempotency key here.
- HTTP transport errors on a send now conservatively mark outcome unknown. HTTPX
  INFO request URLs previously exposed bot tokens: a targeted log redaction filter
  preserves events while masking Bot API credential paths. Regression verifies it.

No schema migration, provider rewrite, frontend edit, sandbox enable or new dependency.
An additive typed server-work signature endpoint is opt-in and503 by default.
The code deliberately commits authority separately from request completion; an HTTP500
may follow an admitted delivery. Clients must read task status, never automatically
repeat approval/send. Uncertain outcomes require human inspection, not a retry button.

## P0–P9 acceptance

| Phase | Code evidence in current repository | Result / remaining acceptance |
|---|---|---|
| P0 | auth edge, owner-managed tokens, RBAC, account quotas; new JARVIS delivery regressions | BLOCKED for release: fresh executor CRITICAL, Electron HIGH, independent review and containment failures; scans below |
| P1 | `student/`, `documents/executor/`, migration0022, real native tests in CI | PARTIAL: OCR/Office is implemented (older matrix saying absent is stale); selected host acceptance, large-scan batching/resume still incomplete |
| P2 | `memory/`, `api/routes/personal.py`, consent/recall changes preserved from PR39 | PARTIAL: per-user persistence exists; full retention/revocation/failure drills need further acceptance |
| P3 | `student/paths.py`, cited comparison/graphs/cards, immutable revisions | PARTIAL: paths use actual reviews; automatic tutor quality/longitudinal evaluation and integrated journeys incomplete |
| P4 | `EXECUTION_GATES.md` and disabled execution boundaries | BLOCKED: no /dev/kvm or approved separate general-code executor; fixed-function document containers are not K4 |
| P5 | proposal/review APIs, protected admin scope | PARTIAL: proposals/static review only; generated-code tests/signing/promotion cannot be enabled without K4 and independent containment review |
| P6 | `learning/refresh*.py`, migration0020 | PARTIAL: durable scheduler/leases/permission fences exist; runtime hosting and independent recovery review outstanding |
| P7 | IELTS sessions/text metrics/STT interface, editable Office and model-planned presentation intake | PARTIAL: real provider quality, pronunciation claims and full output/device acceptance remain unverified |
| P8 | `account/`, migration0024, user tokens/tiers/durable usage_events | PARTIAL: tier quota events are not a monetary provider ledger; public signup/payments remain disabled |
| P9 | `deploy/primary`, `docs/deployment` | BLOCKED for live release; preparation only, no actual4/8GB VM benchmark/cloud restore or inclusive$10 quote |

## K1–K9

| Requirement | Status | Evidence / limitation |
|---|---|---|
| K1 | PARTIAL | bounded authorized source ingestion; initial first-read recovery is distinct from governed refresh |
| K2 | PARTIAL | owned/library-scoped retrieval and revision citations; retrieval-quality/recall evaluation not completed |
| K3 | PARTIAL | proposal-only capability analysis; no execution authority from retrieved content |
| K4 | BLOCKED | guest isolation/control plane and adversarial VM evidence absent; no unsafe fallback |
| K5 | BLOCKED for execution | static skill/proposal work is useful but not an installed/tested skill runtime |
| K6 | BLOCKED for promotion | generated patches must bind K4-tested artifact, owner-approved repository/base/paths/hash; no unattended push/merge/deploy |
| K7 | PARTIAL | durable permission-fenced refresh implemented; external runtime acceptance pending |
| K8 | PARTIAL | Super Admin proposal + durable review/audit exists, not autonomous source mutation |
| K9 | PARTIAL | consent-gated personal memory, goals and recall; complete lifecycle/retention and real multi-device owner acceptance pending |

## Nine upstreams: code is not research

Pins1–8 are historical inspected pins preserved in UPSTREAM_REVIEW.md and
UPSTREAM_IMPLEMENTATION_MATRIX.md. Reuse already merged is retained; no new upstream
scripts executed or source copied in this candidate. FastAPI source inspection was
updated to the actual locked0.156.5 tag, not the older locally installed0.143.3.

| Upstream / source commit | Feature → EZO code → test | License | Result / blocker |
|---|---|---|---|
| LlamaIndex `619d74664e8404612038bc15a1a40c686037277c` | TextNode interoperability → Student context adapter → Student synthesis/context tests | MIT | PARTIAL; TextNode alone does not satisfy measurable retrieval improvement; benchmark and justified retrieval reuse remain engineering work |
| Ruflo `5d99b57e7862c0623cf26e0c152dff60e3b50346` | capability governance → orchestration planning policy → forged/unknown approval negatives | MIT | PARTIAL adapted policy; unrestricted upstream CLI/MCP excluded |
| VoiceStudio `28bf2c7a83b8a64836297340c52a45d716684aed` | separate HTTP STT/TTS adapter → voice service → transport/error tests | AGPL-3.0-only; model terms separate | PARTIAL HTTP interoperability; no copied AGPL source or authorized model weights/live engine acceptance |
| APEX-UI `a8732fad1078a809cadfa810cb0d89cf4445dbed` | typed backend capability contracts → MASTER_API_CONTRACT.md | MIT | PENDING Claude Max frontend ownership; API JSON is not a UI integration |
| REA `c8ed32853881b08aa83459d4da55a28a4e09b0c8` | prerequisite/availability policy → planning_policy.py and companion scope checks → missing authority negatives | MIT root; bundled notices separate | PARTIAL adapted concepts; actual RE engine belongs only in separately authorized isolated Developer Lab |
| Supabase `1055bc6b458d58a7532f03ad2e9ed34983077d40` | private server-only Storage → storage/supabase.py → private origin/ownership/failure tests | Apache-2.0 | PARTIAL; no live cloud lifecycle/restore evidence, full-profile remote outbox still needs review |
| Microsoft JARVIS `7624cf388b47334ff8a0868e7d862dde18cfda86` | bounded tool planning/math → jarvis/planner.py, percentages.py → real Decimal/output tests | root MIT; component license discrepancy recorded | PARTIAL; no unsafe eval/upstream executors, task planning not live delivery evidence |
| OpenJarvis `8f81c024608bacaefc551761196eeb556ab5631e` | typed tools/traces and governed companion → jarvis/device_protocol.py, service.py → real Ed25519/DB + mocked Telegram integration | Apache-2.0 | PARTIAL; Windows/Android owned by Claude, real device/provider acceptance separate |
| FastAPI `43f46fb14feeee78f4077a55eb3f95f792b7cd9d` | existing application/dependency/security composition → main.py, api/deps.py, routes → ASGI auth/ownership/contract suite | MIT | ACTUAL framework integration retained; inspected applications.py and security/http.py at locked0.156.5, no replacement or speculative optimization |

### Exact code/test file index for the upstream matrix

Code paths below are relative to `apps/api/src/ezo_api`; test paths to `apps/api/tests`.

| Upstream | EZO files | Working test files / exclusion |
|---|---|---|
| LlamaIndex | `student/synthesis.py` | `integration/test_student_synthesis.py`; measurable retrieval benefit still unproven |
| Ruflo | `orchestration/planning_policy.py` | `unit/test_jarvis_foundation.py` |
| VoiceStudio | `voice/openai_audio.py`, `voice/service.py` | `unit/test_voice.py`; HTTP doubles, no model service |
| APEX-UI | repository `docs/integration/MASTER_API_CONTRACT.md` only | No APEX implementation test; frontend port pending Claude |
| REA | `orchestration/planning_policy.py`, `companion/metadata.py` | `integration/test_companion_metadata.py`; actual RE engine excluded |
| Supabase | `storage/supabase.py` | `unit/test_supabase_storage.py`; HTTP doubles, no cloud restore |
| Microsoft JARVIS | `jarvis/planner.py`, `jarvis/percentages.py` | `unit/test_jarvis_engine_units.py` |
| OpenJarvis | `jarvis/device_protocol.py`, `jarvis/service.py`, `api/routes/jarvis.py` | `unit/test_signed_device_work.py`, `integration/test_jarvis_tasks.py` |
| FastAPI | `main.py`, `api/deps.py`, `api/routes/accounts.py` | `integration/test_projects_auth.py`, `integration/test_accounts.py` |

## Canonical device/API contracts

See `docs/integration/MASTER_API_CONTRACT.md` (Pydantic request bodies and OpenAPI in
FastAPI remain source-of-truth). Devices currently receive typed `DeviceWork` over authenticated HTTP; only
`SignedDeviceResult` is Ed25519-signed in this protocol. The new opt-in `/work-signed` endpoint signs that existing queue, and
`SignedDeviceWork`/`verify_work` provide device/deadline/tamper verification. It
fails503 without an operator signing key. Existing clients still use the legacy
route; pinned-key enrollment, durable receiver replay journal and rollout remain
engineering/integration work. TLS is not a substitute for those requirements. Types live in `jarvis/device_protocol.py`;
capability is currently a fixed
Downloads document action, never arbitrary paths/commands. Pairing is Ed25519 proof
of possession plus short-lived owner confirmation. No Android/iOS unrestricted
control claim. Existing desktop/mobile UX and voice providers are unchanged.

Delivery contract addendum: task/step IDs and exact scope hash bind approval.
`receipt.delivered` contains only verified provider results. A persisted
`receipt.delivery_state=dispatching` is **not** success. Terminal
`error_code=delivery_unknown` means inspect receipts/provider before taking any new
explicit action. `artifact_changed` means nothing was sent. Repeated decisions,
failed delivery retry and stale authority do not grant a new send.

## Acceptance evidence / operating rules

Focused local JARVIS/delivery/signature regression suite:28 passed on the synchronized locked environment.
Before fixes:2 new delivery regressions failed. Test doubles: Telegram HTTP only;
real ASGI requests, SQL transactions, Ed25519 and PDF artifacts. No live provider call.
Full SQLite/PostgreSQL, migration, Security, Docker/native and Devices results are
recorded with exact candidate SHA in the accompanying evidence report; **not yet
claimed passing by this document**. Historical CI links in older documents are not
new runs. CI/Security/Devices branch triggers added without changing thresholds.

Local environment initially had stale dependencies; uv sync --frozen corrected it.
Interrupted preliminary runs are not successes. OCR test with default local packs
failed0.9 recall threshold; using the existing reviewed TESSDATA_PREFIX passed the
same unmodified test. Full reruns use that explicit language-pack environment.

Required independent review: SQL commit boundary change, partial delivery, concurrent
cancel/revocation and stale dispatch recovery. Uncertain delivery is intentionally
not retried. No claim that public Bot API metadata proves the recipient opened a file.

## Remaining engineering work vs external authorization

Independent code work still remains: client adoption of the new signed device-work endpoint with pinned
server trust and a durable replay journal (result/pairing proofs alone do not satisfy it); true provider token/audio/cost accounting
(across processes, distinct from daily entitlement counters), durable worker
admission/cancellation for every native action, long-scan batches/resume, measured
LlamaIndex retrieval improvements, full retention/lifecycle and privacy-sharing
policy coverage. These are not falsely labelled owner-credential blockers.

External gates: approved VM runtime and containment review for K4; owner PC/phone
camera/mic/speakers; live AI/STT/TTS keys; Telegram bot and supported recipient
start-code enrollment; selected executor host; VoiceStudio/model legal clearance;
cloud backup/restore, exact recurring quotes including backups/egress/taxes and
release signing. No guaranteed$10 budget or official IELTS band without evidence.
No credential creation, public registration/payment activation, provisioning,
production deployment, branch protection change or automatic merge performed.

## Verified candidate snapshot (backend source7cb4e31)

Final local suites (locked dependencies, explicit reviewed OCR language packs):
SQLite **1363 passed /54 skipped**; PostgreSQL **1378 passed /39 skipped**; focused
JARVIS/signature tests **28 passed**. Ruff/format pass (528 files), mypy344 modules.
Alembic: both databases0024, no new upgrade operations. No schema changes here.
The API image source tree and all117 audited runtime dependency versions match.
Python audit117/0 advisories; production Node audit0; gitleaks265 commits/0 leaks
at the backend-code checkpoint. Final evidence archive records later docs/CI head.

Actual API image build/smoke PASS: UID10001, networknone, read-only/capdrop/no-new-
privileges,768MiB/1CPU, test settings inside the production image. Native processing
remains OFF in API, with no Tesseract/soffice. lxml6.1.3 embeds libxml2 runtime and
compiled2.14.6. This is not production DB/TLS or a live provider acceptance test.

Actual executor image build PASS. Quiescent real-container document subset:
**12 passed /19 deselected**, covering PDF/DOCX/EPUB citation offsets, five OCR
language cases, multi-page scan numbering and DOCX/XLSX/PPTX→PDF. Separate aggregate
memory recheck: **1 passed**. Counts are distinct runs, not additive coverage totals.

**Full native containment suite did not pass:** interrupted after **5 passed,
31 failed**. The first failure is the unchanged15-second Docker-create deadline
on this VFS daemon; fresh/stalled reservation then caused cascading failures.
This is not proof every subsequent failure is environmental. Preserve the complete
failure log, rerun on a suitable selected host, and review all remaining failures.
Neither deadlines nor assertions were weakened. Partial successful reruns do not
replace full containment acceptance. Fixed-function containers are never K4 proof.

Web Docker build BLOCKED at mandatory Alpine apk upgrade (HTTP403, exit99).
No frontend Dockerfile or upgrade gate was changed. Hosted CI/Security/Devices
NOT RUN on this candidate: git push lacks write authentication, GraphQL PR creation
returns Forbidden. A verified Git bundle is supplied; no remote branch/PR is claimed.

### Current security release blockers

| Finding | Verified evidence | Reachability / decision |
|---|---|---|
| Native **CRITICAL CVE-2026-6653** | libxml2 `2.12.7+dfsg+really2.9.14-2.1+deb13u3` in fresh executor; Trivy advertises no fixed Debian version | UAF in XML parsing; Office XML processing makes this relevant. EZO exploit reachability is not proven. Isolation mitigates blast radius, not the vulnerable package; independent review/vendor fix or reviewed backport required |
| API44 HIGH /0 CRITICAL; executor80 HIGH /1 CRITICAL | Fresh official GHCR Trivy database; zero findings with a vendor fixed version among HIGH/CRITICAL | No suppression/ignore-unfixed; passing the unchanged fixable-CVE gate is not release approval |
| **HIGH CVE-2026-115570 / GHSA-jr5w-w6x2-84p9** | Electron44.7.0, patched>=44.9.1, npm advisory: compromised eMudhra intermediate mitigation | Electron ships in Windows app even though declared devDependency. Claude owns desktop dependency patch and Windows acceptance. API cert mitigation does not patch Electron |
| MODERATE CVE-2026-41907 / GHSA-w5hq-g745-h8pq | uuid7.0.3 via mobile>@capacitor/cli>xcode; patched>=11.1.1 | Build-tool dependency, no EZO exploit demonstrated. Coordinate compatible upstream/tooling upgrade; do not force a breaking major override to hide it |

The security workflow now builds/scans the **executor as well as API and web**.
It also fails HIGH/CRITICAL packaged Electron findings from node-all.json despite
production-only audit passing. Current local Electron gate correctly exits1 on
the actual advisory. Thresholds have not been weakened; expect that new check to
remain red until the coordinated desktop patch is made. Workflow YAML parses,
but its new hosted execution is unverified because publishing is blocked.

**Release verdict: BLOCKED.** These are code/security, runtime, ownership and
external-validation gates; not merely missing production credentials. No claim
that P0–P9 or K1–K9 is fully finished. No merge, deployment or purchase performed.
