# EZO OS — independent master audit (Claude, 2026-10-23)

- **Audited code:** `main` at `38c752c8a469fbddb6db00bbff6f75af82ee7b13` (merge of PR #27).
- **Remediation:** on `claude/master-audit-remediation` (PR #28). See
  [CLAUDE_REMEDIATION_REPORT.md](CLAUDE_REMEDIATION_REPORT.md).
- **Not independently reviewed.** The same author wrote this audit and the fixes, so neither is
  self-certified. An independent reviewer (Codex or a human) must check both before merge.
- **No merge, deploy, purchase, billing, credential creation or branch-protection change was made.**

## 1. Method

| Area | How it was checked |
|---|---|
| Security | Read every route, migration and worker added in PRs #10–#27 (262 files, +31,305 lines).<br>Ran the API suite on SQLite (1186 passed, 68 skipped) and PostgreSQL (1201 passed) in a scratch copy.<br>Probed the legacy launcher (D4) by experiment. |
| JARVIS / devices | Compared the app's OpenAPI schema with every path the UI and extension call.<br>Sent a real request to each path through the ASGI app.<br>Checked CORS headers.<br>Read git history for the prototype (539e876 → 2d15a12). |
| Frontend ↔ backend | Built a page-by-page contract table (every `fetch` against every route schema).<br>Ran i18n key parity.<br>Mapped Playwright coverage. |
| Product (P0–P9) | Ran runtime probes with the real `create_app()` and the test-only native fixture context **switched off**, which is the production default. |
| Upstreams | Shallow, read-only clones of all nine repositories.<br>Compared licences byte-for-byte with EZO's copies.<br>Mapped each claimed feature to EZO files and tests. |
| Hosting | Checked vendor pages directly where the proxy allowed.<br>Everything else comes from search summaries, marked as such. Nothing was bought. |

The probe scripts and raw agent reports are session scratch files. They are summarised here because
they are not committed.

## 2. Process findings (the root causes)

1. **18 PRs (#10–#27, about 31k lines) were merged with zero reviews.** Several of them made claims
   the code did not support.
2. **The published API contract was ignored.** `docs/integration/MASTER_API_CONTRACT.md` already listed
   the real JARVIS endpoints. The Antigravity JARVIS page and the Chrome extension were built against
   11 endpoints that never existed in any commit.
   - Correction of my own earlier statement: I first said this contract file did not exist. It does.
     Only the relative link in `ACCEPTANCE_MATRIX.md` was broken, and that link is now fixed.
3. **The tests do not test the runtime that ships.** `apps/api/tests/conftest.py:109-116` turns on
   `trusted_native_regression_fixtures()` for the whole session. As a result, the many OCR, Office, PDF
   and chat-document tests pass in CI, while production hides 14 tools and accepts only
   TXT/MD/CSV uploads.
4. **CI on `main` was red** (run #202). The cause was infrastructure: the Ubuntu mirror ran at about
   50 KB/s, and the 15-minute step limit cut off the LibreOffice download. No test was failing.

## 3. Findings, ranked by severity

Status: **FIXED** = fixed in PR #28 with a regression test or reproduction.
**OPEN** = not fixed; the reason is given.

| # | Sev. | Finding | Evidence | Status |
|---|---|---|---|---|
| F1 | Critical (product honesty) | The JARVIS page invented a paired, online "Windows 11 / OpenJarvis" device whenever the fetch failed, which happened every time: `credentials: "include"` + API `allow_credentials=False`. The "Paired" badge was unconditional. | `JarvisPage.tsx:99-110,126-136,296-299` @38c752c; CORS probe | FIXED (page rebuilt on the 4 real routes) |
| F2 | High | All 6 JARVIS page endpoints and all 5 extension endpoints returned 404. | OpenAPI + ASGI probe | FIXED (UI uses only real routes) |
| F3 | High (latent) | Fabrication template: a hard-coded Telegram recipient and phone number, and any `receipt_id` shown as "Yetkazildi" (delivered). The approval was not bound to anything. | `JarvisPage.tsx:417-430,552-556` | FIXED (removed) |
| F4 | High (docs) | `ROADMAP.md` said "JARVIS … Reference scenario verified end-to-end". | `ROADMAP.md:252-259` | FIXED (rewritten as foundation only) |
| F5 | High (privacy) | The Chrome extension injected a content script into every `http(s)` site and called non-existent endpoints. | `manifest.json:23-27` | FIXED (permissions `["storage"]` only; one authenticated read-only call) |
| F6 | High (CI) | `main` CI timed out on apt. | Run #202 log | FIXED (cache + bounded attempts + mirror fallback; runs #203/#204 green) |
| F7 | Medium | The Student concept graph crashed on every response, because the UI expected a different shape. | `StudentPage.tsx:74-85` vs `synthesis.py:239-252` | FIXED |
| F8 | Medium | Student showed an invented 7-day plan and sample flashcards ("Fotosintez"), with no way to create real cards. | `StudentPage.tsx:112-117,307-317` | FIXED (`/practice-plan`, source-checked card proposals → `POST /cards`) |
| F9 | Medium | Every presentation layout collapsed to `bullets`: the layout was checked against `THEMES` instead of `LAYOUTS`. | `presentations.py:176` | FIXED (+ regression test) |
| F10 | Medium | Admin proposal list fields were nested under `proposal`, so the UI was blank; decisions never shown. | `improvements.py:255,278` | FIXED (+ test) |
| F11 | Medium | Presentation downloads were plain links, so they returned 401 in token mode. | `PresentationsPage.tsx:291-308` | FIXED |
| F12 | Medium | IELTS recorded 30 s of invented speech per typed answer and showed "Band  - ". | `IeltsPage.tsx:94,212,401` | FIXED |
| F13 | Medium | The memory page's stats keys and goal categories/status differed from the API (422 silently ignored). | `MemoryPage.tsx` vs `schemas/personal.py` | FIXED |
| F14 | Medium | The admin page invented system values (PostgreSQL / Aktiv / v0.2.0). | `AdminPage.tsx:323-373` | FIXED |
| F15 | Low | Card delete (204) was reported as an error. | `student-api.ts:9` | FIXED (+ unit test) |
| F16 | Low | `NODE_OPTIONS` was in the Ruflo child env allowlist (code loading via `--require`). | `orchestration/security.py` | FIXED (+ test) |
| F17 | Low | Free beta: `/admin` was in the nav although not allowlisted; consent could not be granted (`auto_memory` 409); `/api/beta-profile` was allowlisted but missing. | `HistoryPanel.tsx`, `MemoryPage.tsx`, `free_beta.py` | FIXED |
| F18 | Medium (privacy) | Revoking memory consent does not stop **recall** of memories already saved into prompts. | `core/ezo_core.py:589-599` | OPEN — owner decision D-07: gating recall would also hide explicitly saved memories. |
| F19 | Medium (product) | Chat-driven DOCX/XLSX/PPTX, OCR, PDF tools and Office→PDF are denied in production. With the fake provider the agent still replied "Taqdimot tayyor." ("Presentation ready"). | Probe `probe_chat3.py` | OPEN — needs the separate reviewed executor host (P1/P7) |
| F20 | Low | Legacy XLSX opened in-process on the event loop, bypassing the isolation gate (only for XLSX stored before the upgrade). | `agents/convert_office.py:204-214` | OPEN |
| F21 | Low | Office spreadsheet rows/cells have no type or size bound (owner-only memory pressure). | `schemas/office.py:31` | OPEN |
| F22 | Low | Raw Student uploads (5 MiB each) have no quota while no worker runs. | `student/ingestion.py` | OPEN |
| F23 | Low | Local (no-token) mode: a cross-site `text/plain` POST can queue uploads. Production refuses local mode. | `api/routes/student.py:110-114` | OPEN |
| F24 | Low (legacy) | D4 `setsid` escape and D6 4 GiB `RLIMIT_AS` are still in the legacy launcher. Not reachable in production: `require_isolation()` fails closed and the image has no binaries. | `process_limits.py:30-40` | OPEN — remove the launcher when the executor is accepted |
| F25 | Low | The IELTS cue card a user selects is ignored, because the API has no field for it. | `IeltsPage.tsx:496-500`, `schemas/ielts.py:20` | OPEN (API change) |
| F26 | Low | Admin, JARVIS and Student pages are Uzbek-only; 35 i18n keys are unused. | i18n scan | OPEN |
| F27 | Info | The VoiceStudio compose service uses the moving `:stable` tag and an optional key. | `docker-compose.yml` | OPEN — pinning needs a digest (registry blocked here); a required key would break `compose config` in CI |

**Security verdict (backend):** no critical, high or medium exploitable vulnerability was found in
the new code.
- Every new route is owner-scoped, and IDOR checks are present (each `session.get` is followed by a
  `user_id` check).
- `super_admin` can only be granted by the offline CLI, and the server enforces it per request.
- Governance cannot execute, install, push or merge.
- Earlier findings D2, D3 and D5 are fixed; D7 is mitigated.

## 4. JARVIS Mode — what is real

- **Removed and must stay removed:** the prototype `jarvis/telegram.py` (hard-coded contact "baxtiyor",
  `status="delivered"`, `tg_rcpt_` ids), its pairing token `ezo_oj_token_sec_9841` and fixture seeding.
  These were deleted in `2d15a12` and are confirmed absent at HEAD. The UI template that would have
  displayed them was removed in this PR.
- **Real today:**
  - `GET /api/jarvis/capabilities`: every device feature reports `available: false` together with its
    missing prerequisites.
  - `POST /api/jarvis/percentages`: exact Decimal arithmetic on numbers the user types, with a stored
    receipt (hashes only).
  - `GET /api/jarvis/receipts/{id}`.
  - `POST /api/jarvis/inspect-plan`: static inspection; nothing executes.
  - A Linux-only metadata companion CLI with Ed25519-signed messages. It is **not wired to the API**.
- **Not implemented:** voice command → Windows Downloads → two-file comparison → PDF → Telegram send.
  There is no pairing, device registry, task queue, executor, Windows/Chrome/mobile control or
  Telegram provider.
- **No Telegram delivery and no Windows or mobile control is claimed.** None exists, and there is no
  real-device or provider evidence.

## 5. Nine upstreams (UPSTREAM → FEATURE → FILES → TEST → STATUS → LIMITS)

| Upstream | Feature | EZO files | Actual test | Status | Limitations |
|---|---|---|---|---|---|
| FastAPI | Web framework | Whole API (`main.py`, 30 route modules) | About 26 test files over ASGI/TestClient; CI | **IMPLEMENTED** | 0.143.3 is pinned; upstream is at 0.161.1 |
| LlamaIndex | `TextNode` interchange | `student/synthesis.py::llama_nodes`, `/api/student/context` | `test_student_synthesis.py`: proves the output shape, not LlamaIndex behaviour | **PARTIAL (thin)** | No retrieval, parsing or evaluation use; 35 extra distributions; no agent consumes `/context` |
| Ruflo | Capability restriction that can only narrow | `orchestration/planning_policy.py`, `tool_plan.py` | `test_restriction_cannot_widen_tools_actor_or_deadline` | **PARTIAL (concept port)** | CLI/MCP excluded (CVE-2026-59726, `terminal_execute`); `NODE_OPTIONS` allowlist fixed (F16) |
| VoiceStudio | OpenAI-compatible STT/TTS over HTTP | `voice/openai_audio.py`, `voice/service.py`, compose profile `voice` | Real SDK against `MockTransport` (wire format only) | **PARTIAL** | AGPL-3.0 (no code copied: HTTP aggregation only); default OmniVoice weights are **CC-BY-NC**; no live engine; no Uzbek quality test |
| APEX-UI | UI patterns | none | none | **NOT STARTED** | The "APEX Dock" from 539e876 was reverted. Two 21st.dev components have unknown authors: do not copy them |
| REA | Telling missing prerequisites apart from tool presence | `planning_policy.py::availability` (5 lines) | Missing-prerequisite tests | **CONCEPT ONLY** | No REA runtime. Use is restricted to authorized, isolated Super Admin development |
| Supabase | Private Storage REST, PG/pgvector | `storage/supabase.py`, `deployment.py`, `deploy/*.sql` | Mock-transport contract tests | **PARTIAL** | No live project. The legacy 400-for-`not_found` error format is unhandled. No backup or restore drill |
| Microsoft JARVIS | Tool cards, arithmetic tool, tool graph | `tools/percentage.py`, `tool_plan.py`, `routes/jarvis.py` | `test_jarvis_foundation.py`, `test_jarvis_api.py` (real) | **PARTIAL (concept)** | No executor. Upstream `funcQA.py` `eval()` must never be imported |
| OpenJarvis | Typed tools, receipts, signed local ops | `routes/jarvis.py` receipt, `companion/protocol.py`, `companion/metadata.py` | `test_companion_metadata.py` (22, real processes, Linux) | **PARTIAL** | Linux only; not wired to the API; no pairing; no Windows/Chrome/mobile/Telegram |

The fact that all nine were researched does **not** mean they are integrated. Only FastAPI is fully
implemented. The full table with pins and licences is in `UPSTREAM_IMPLEMENTATION_MATRIX.md`.

## 6. P0–P9 acceptance (verified)

| Phase | Status | Proof / gap |
|---|---|---|
| P0 Baseline & security | PARTIAL | CI and Security are green on the PR #28 head (see the remediation report). Gap: tests use the native fixture exception, and distro CVEs are recorded. |
| P1 Student Deep Reading V1 | PARTIAL | Text path works with cited answers. PDF/DOCX/EPUB need the dedicated Docker worker; none of the 17 isolated-executor tests ran without the pinned image. No OCR. |
| P2 Personal Intelligence K9 | PARTIAL | Consent, CRUD, export and goals work. F18 is open. No retention policy. The router corpus has 17+3 cases. |
| P3 Student V2/V3 | PARTIAL | Synthesis, graph, cards, paths and progress work. The scheduler is a simple multiplier (not SM-2/FSRS). The graph is not persisted. Paths are written by the owner. |
| P4 K4 Sandbox | BLOCKED | No sandbox. Needs a separate VM/microVM; `/dev/kvm` is unavailable. |
| P5 K5/K6/K8 | PARTIAL (K6 not started) | Proposal and static-draft review only; no code generation or PR flow. |
| P6 K7 Refresh | PARTIAL | 34 tests. The worker is not auto-started. Learned sources only. |
| P7 IELTS / Presentation / Office 2.0 | PARTIAL | REST exports work. IELTS REST is text-only with no scoring. Presentation intake is a fixed template. Chat Office tools are denied in production (F19). |
| P8 Premium UX & multi-user | PARTIAL / multi-user NOT STARTED | Single owner. Rate limits are in memory. No tiers or quotas. i18n is missing on 3 pages. |
| P9 Cloud integration | NOT STARTED (unauthorized) | Preparation docs only. Deployment needs separate owner approval. |

## 7. Feature matrix

**WORKS NOW (production runtime, no keys)**
- TXT/MD/CSV knowledge upload, keyword retrieval with citations, revisions and provenance.
- Student text reading; flashcard CRUD and review; practice plan; progress counts.
- Memory CRUD, export and opt-in consent; goals.
- Office REST: DOCX (+ EZO-rendered PDF) and XLSX/CSV; artifact versions and downloads.
- Presentation REST: PPTX/PDF/HTML with real layouts (after F9).
- IELTS text session flow (no score).
- JARVIS percentage calculator with receipts.
- K1 web/GitHub/PyPI/npm text learning; K3/K8 proposals.

**WORKS WITH CONFIGURATION**
- AI answers, guides, quizzes, synthesis, concept graph and flashcard proposals: an
  OpenAI/Anthropic/Gemini key.
- Semantic search: an embedding key.
- STT/TTS: an ElevenLabs, OpenAI or VoiceStudio key. Uzbek TTS is unverified.
- Student PDF/DOCX/EPUB: dedicated worker host + PostgreSQL + Docker + pinned image.
- K7 scheduled refresh: `refresh_cli` must be run.
- Chrome extension status popup: an API URL and token.

**PARTIAL**
- Concept graph; cross-document comparison (excerpts only); adaptive paths (manual).
- Consent (does not gate recall); AI cost control (per-process counts, no ledger).
- Presentation intake (template); K5/K8.

**BLOCKED / DISABLED**
- OCR; PDF tools; DOCX editing; LibreOffice conversion; uploads of PDF/DOCX/XLSX/images to the API.
- Chat-created Office files and images; K4 sandbox; K6; realtime voice.
- Multi-user tiers; P9 cloud.
- The whole JARVIS device / Telegram scenario.

## 8. Device, browser and authorization report

| Surface | State | Evidence |
|---|---|---|
| Desktop browser (Chromium) | Works against the real API | Playwright 43/43 locally; CI web job |
| Mobile browser (viewport) | Layout works | `mobile.spec.ts` (viewport emulation, not a real phone) |
| Chrome extension | Status only: shows API capabilities with a bearer token. No page access, no host permissions, no actions. | `apps/web/lib/chrome-extension.test.ts`. Not loaded into a real Chrome profile in this session. |
| Windows companion | **Does not exist.** `companion/metadata.py` refuses Windows. | No real-device evidence |
| Linux companion | CLI only, manual key pinning, not callable from the API | `test_companion_metadata.py` |
| Mobile app / phone control | **Does not exist** | — |
| Telegram | **Does not exist.** No provider, token or delivery. | — |
| Authorization | Single-owner bearer token (`hmac.compare_digest`) checked at the edge before the body is read. Production refuses tokens under 32 characters or non-token mode. `super_admin` is granted only by the offline CLI and checked server-side. The UI is not role-aware and relies on the server's 403. | Security audit §1 |

## 9. Full Owner Beta deployment readiness

**Verdict: suitable for personal, single-owner use on a private host for the WORKS NOW features.
NOT ready for public release.**

Blockers before public release:
- multi-user accounts and quotas;
- a durable AI cost ledger;
- consent gating of recall (F18);
- the reviewed native executor (P1/P7);
- a restore-tested backup;
- independent review of PRs #10–#28.

Deployment remains unauthorized (P9).

**$10/month architecture (recommended B, about $7.2–8.6 per month all-in; not purchased, prices from
2026-10-23 search summaries):**
- Hetzner CX23 (2 vCPU / 4 GB, €5.49 + €0.50 IPv4) as the primary: Caddy + web + API + PostgreSQL/pgvector
  + text worker. Owner data lives here.
- Oracle Always Free A1 as a separate executor: dockerd + gVisor `runsc` (systrap, no KVM needed), no API
  keys, connected over WireGuard. Note that **the A1 allowance was halved to 2 OCPU / 12 GB on 2026-06-15**.
- Cloudflare R2 (≤10 GB free) for restic + `pg_dump` backups. The restore must be tested before real data
  goes in.

**What does not fit in $10:**
- A fully paid two-host stack: +$4.4 to +$7.1 per month.
- A microVM per job (Firecracker needs `/dev/kvm`).
- Any PaaS with 2–4 GB of RAM.

Owner checklist:
1. Check live checkout totals.
2. Confirm the A1 quota and capacity in the console.
3. Build arm64 images in CI.
4. Run `scripts/benchmark_owner_stack.py` on the real VMs.
5. Restore-test the backup.
