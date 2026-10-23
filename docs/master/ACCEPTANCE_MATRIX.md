# Integrated master acceptance matrix — candidate, not product completion

Baseline integration **c3303d94c128406dfd286168cd9dd02079c61f1a**. Existing Draft
[PR21](https://github.com/UmidjanDeveloper/EZO/pull/21) foundation
**3ec6cf1cfc7e90588f8c3c2a033a255c3ff70c0b** is preserved as an ancestor.
No merge or deployment is authorized or performed by this candidate.

## Authoritative P0–P9 mapping

Statuses re-verified by the independent audit of 2026-10-23 at `38c752c`; evidence and
findings are in [CLAUDE_MASTER_AUDIT.md](CLAUDE_MASTER_AUDIT.md) §6.

The owner has now supplied [the actual master roadmap](OWNER_ROADMAP_P0_P9.md).
The earlier missing-document gate is resolved. Its original DOCX hash is recorded
with the extraction; historic technical claims remain historic. Additional owner
requirements (eight upstreams and governed device agents) remain in force.
These statuses describe acceptance, not just whether source files exist.

| Phase | Owner's scope | Current acceptance status / gate |
|---|---|---|
| P0 | Baseline and security | PARTIAL — local/hosted regression evidence exists; current changes need independent review; unresolved distro CVEs remain recorded. |
| P1 | Student Deep Reading V1 | PARTIAL — text path and citations work; PDF/DOCX/EPUB need the dedicated Docker worker (its executor tests skip without the pinned image). Review candidate [P1_EXECUTOR_OCR_OFFICE.md](P1_EXECUTOR_OCR_OFFICE.md) adds scanned-PDF/PNG/JPEG OCR (eng/uzb/uzb_cyrl/rus, ≤6 pages, refused above) and DOCX/XLSX/PPTX→PDF inside that isolated executor only; not activated, needs independent review and dependency review. No OCR in the API image. |
| P2 | Personal Intelligence K9 | PARTIAL — consent, memory, goals and routing exist; full owner journeys and reviewed multi-user readiness remain. |
| P3 | Student V2/V3 | PARTIAL — cited synthesis/graphs/cards/recall progress exist; longitudinal adaptive tutor quality and integrated UI remain. |
| P4 | K4 Secure Sandbox | BLOCKED — execution remains disabled without a validated separate Python-compatible trust boundary. |
| P5 | K5/K6/K8 Admin Engine | PARTIAL — backend admin proposals/static drafts/reviews exist; sandbox tests and governed application PR promotion remain gated. |
| P6 | K7 Knowledge Refresh | PARTIAL — durable permission-fenced refresh under implementation; verification and independent review required before acceptance. |
| P7 | IELTS / Presentation / Office 2.0 | PARTIAL — REST DOCX/XLSX/PPTX exports work (deck layout bug fixed in PR #28); IELTS REST is text-only: per-answer metrics labelled with the part actually answered, and on completion per-part observations plus numbers-only overall statistics (words, lexical diversity, fillers, repeats; pace only from *client-reported*, unverified time). Thresholds are non-official EZO practice heuristics; no audio is analysed and band/pronunciation/model scores stay null; presentation intake is a fixed template; chat-driven Office/presentation tools are denied in production. |
| P8 | Premium UX and multi-user readiness | PARTIAL — single owner only; multi-user accounts, tiers and quotas NOT STARTED; Admin/JARVIS/Student pages not internationalised. |
| P9 | Final cloud integration | NOT STARTED / BLOCKED — preparation documents only; deployment needs separate owner approval. |

No numerical completion percentage is invented. The following detailed rows retain
specific implementation and quality limitations. The original roadmap is a floor,
not a waiver of later owner requirements or an assertion that these features work.

| Requirement | Actual implementation / candidate evidence | Unresolved acceptance gate |
|---|---|---|
| Preserve P0 security foundation | Auth edge guard, source limits, immutable revisions, dedicated Student parser, existing tenant regression suites retained. Full profile now also refuses privileged DB role before migration. | Unpatched distro HIGHs; native execution still requires reviewed separate host. General sandbox is absent. |
| Preserve Student V1 / P1–P2 foundation | Existing upload/queue/retry/cancellation/reading/semantic-index APIs unchanged. Additive migration0019 only; old0018 remains upgrade predecessor. | Real provider quality, backup/restore drill, native hosting acceptance. No migration history rewrite. |
| Student V2 retrieval / synthesis | Existing K1/K2 hybrid pgvector/keyword reuse; new bounded cross-document comparison with citations from every selected source. | Excerpt-based only. Whole-book completeness and contradiction entailment not established. Authorized website ingestion remains K1's existing bounded crawler. |
| Student concept graphs | Typed bounded graph, unique nodes, valid edges, exact source quotes; real configured model request, no canned output. | Relationships/labels are generated interpretations; no live model quality evaluation, graph UI or persisted graph version history yet. |
| LlamaIndex integration | Pinned core TextNode interop for validated, owned context; no external agent/loader/eval surface. | 35 extra distributions, measured import overhead, ongoing dependency/license review. Not a replacement of EZO ACLs/vector ownership. |
| Personal tutoring / multilingual learning | Existing answer, guide, summary, quiz in uz/en/ru retained; new source-validated flashcard proposals. Provider errors/offline are explicit. | Owner-defined source-bound recall paths now persist prerequisites and adapt to actual recent reviews. Automatic curriculum generation, validated diagnostics/pedagogical quality and Antigravity UX remain pending; no mastery claims. |
| Durable flashcards / spaced repetition | Explicit source-bound cards, bounded-recall-v1 schedule, version fences, review event idempotency, real counters and user-confirmed deletion. | Backend only; Antigravity practice UI pending. Self-reported recall is not validated mastery. Revision invalidation and deletion apply. |
| Student V4 advanced learning | Source/progress primitives now available without overwriting V1. | Owner-defined prerequisite sequencing is implemented in Student paths. Longitudinal evaluation, validated adaptive tutoring and full multi-agent application workflows remain incomplete; no V4 completion claim. |
| Safe inter-agent knowledge | Authenticated read-only, bounded context with immutable source IDs and explicit no-authority trust label. | Receiver must preserve its own authorization/consent gates. No claim of a fully integrated multi-agent runtime. |
| Isolated OCR / Office | Student dedicated parser now also OCRs scans/images and converts OOXML→PDF inside the verified workload (review candidate, see P1_EXECUTOR_OCR_OFFICE.md); API native execution remains disabled. | Container evidence is CI-only; mixed text/scan PDFs, >6-page scans (batching), handwriting and API wiring of conversion are open. Do not enable legacy API native paths as a fallback. |
| Knowledge K1–K3 | Existing source/library ownership, index, provenance, versions, citations and proposal-only analyzer reused. | Source coverage/freshness and model entailment have bounded guarantees. See existing tests, not documentation labels alone. |
| Knowledge Refresh / K7 | Migration0020 durable refresh runs, explicit permission generations/schedules, leased claims, atomic staged publication, bounded history, per-document stale labels and cleanup journal. See K7_DURABLE_REFRESH.md and actual regression evidence. | Independent review/hosting acceptance pending. Initial K1 first-read runner remains legacy; native PDF/OCR/Office still needs the separate reviewed executor. The new worker is explicit and is not auto-started. |
| K4 general-code sandbox | **Not implemented/enabled.** Existing parser accepts a fixed data protocol, not generated programs. Design in EXECUTION_GATES.md. | Dedicated microVM/VM runtime, trusted build chain and adversarial containment evidence required. Missing /dev/kvm and no approved remote executor; no unsafe substitute. |
| K5 Skill Builder | K3 and admin proposals remain non-executable data. | Code generation, isolated tests, signed skill artifacts and installation blocked on verified K4. No fake successful test/status. |
| K6 branch/tests/PR workflow | This candidate itself uses reviewable commits and CI; proposed promotion contract documented. | General app-controlled skill PR workflow not implemented. No unattended git, merge, secret access or deployment. |
| K8 Super Admin | New backend-only capability proposals from owned libraries, bounded immutable snapshots, hash-bound owner review/reject decisions and audit. No execution authority. | Sandbox tests and source improvement blocked on K4/K5/K6; no complete autonomous self-improvement claim. Independent review still required. |
| AI orchestrator | PR21 Gemini/OpenAI/optional Claude chat+embedding adapters, task routing/fallback/budgets; ElevenLabs STT/TTS and existing VoiceStudio interface preserved. | Process-local caps aren't a durable billing ledger; no hard dollar guarantee, live quality or realtime voice implementation. Cloud privacy allowlist per request not implemented. |
| Personal Intelligence / IELTS / Presentation / Office / Admin | Prior routes retained, consent and owner scope preserved; honesty fixes stay in PR21. | Dedicated IELTS voice/scoring incomplete; presentation intake is a deterministic template, not researched AI output. Office PDF/OCR unavailable without reviewed worker integration. |
| Supabase / persistence | Existing private server-only Storage adapter, TLS checks, pgvector, migrations, local durable full profile retained.0019 revokes PUBLIC/anon/authenticated table grants. | Full-profile remote object lifecycle/outbox and cleanup are not yet reviewed; full profile still refuses that storage mode. Backup restore not exercised against a real cloud project. |
| Antigravity integration | Existing frontend untouched; additive [docs/integration/MASTER_API_CONTRACT.md](../integration/MASTER_API_CONTRACT.md) published for review. | No external review/acknowledgment received. New backend features have no newly integrated frontend. No connected Antigravity review channel is available; the contract is delivered in the repository. |
| Deployment / $10 / P9 preparation | Existing FULL_OWNER_BETA architecture, future owner guide and benchmark protocol retained; expanded gates below. No services created. | No actual4/8GB VM benchmarks, current vendor/tax quotes or safe two-host architecture certified within $10. No production-ready/full-roadmap verdict. |

Final validation evidence and failures are recorded in VALIDATION.md. Passing CI
cannot convert any unresolved product or containment gate above into completion.
