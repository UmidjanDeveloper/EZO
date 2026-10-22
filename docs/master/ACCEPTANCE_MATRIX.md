# Integrated master acceptance matrix — candidate, not product completion

Baseline integration **c3303d94c128406dfd286168cd9dd02079c61f1a**. Existing Draft
[PR21](https://github.com/UmidjanDeveloper/EZO/pull/21) foundation
**3ec6cf1cfc7e90588f8c3c2a033a255c3ff70c0b** is preserved as an ancestor.
No merge or deployment is authorized or performed by this candidate.

## Roadmap identity gate

The owner names a P0–P9 Master Roadmap, but the checked repository's ROADMAP.md
explicitly calls itself the only roadmap and defines Phase 0–14 plus K1–K7.
No P0–P9 master definitions were found in tracked docs or the five available
pasted attachments. **P0–P9 numerical completion cannot be certified without that
source of truth.** This matrix uses the master's explicit capability requirements
instead of inventing a mapping. Historic phase completion and CI results are not
proof of current release readiness. P9 stays preparation only.

| Requirement | Actual implementation / candidate evidence | Unresolved acceptance gate |
|---|---|---|
| Preserve P0 security foundation | Auth edge guard, source limits, immutable revisions, dedicated Student parser, existing tenant regression suites retained. Full profile now also refuses privileged DB role before migration. | Unpatched distro HIGHs; native execution still requires reviewed separate host. General sandbox is absent. |
| Preserve Student V1 / P1–P2 foundation | Existing upload/queue/retry/cancellation/reading/semantic-index APIs unchanged. Additive migration0019 only; old0018 remains upgrade predecessor. | Real provider quality, backup/restore drill, native hosting acceptance. No migration history rewrite. |
| Student V2 retrieval / synthesis | Existing K1/K2 hybrid pgvector/keyword reuse; new bounded cross-document comparison with citations from every selected source. | Excerpt-based only. Whole-book completeness and contradiction entailment not established. Authorized website ingestion remains K1's existing bounded crawler. |
| Student concept graphs | Typed bounded graph, unique nodes, valid edges, exact source quotes; real configured model request, no canned output. | Relationships/labels are generated interpretations; no live model quality evaluation, graph UI or persisted graph version history yet. |
| LlamaIndex integration | Pinned core TextNode interop for validated, owned context; no external agent/loader/eval surface. | 35 extra distributions, measured import overhead, ongoing dependency/license review. Not a replacement of EZO ACLs/vector ownership. |
| Personal tutoring / multilingual learning | Existing answer, guide, summary, quiz in uz/en/ru retained; new source-validated flashcard proposals. Provider errors/offline are explicit. | Adaptive curriculum and validated pedagogical quality not implemented. No model-generated mastery claims. |
| Durable flashcards / spaced repetition | Explicit source-bound cards, bounded-recall-v1 schedule, version fences, review event idempotency, real counters and user-confirmed deletion. | Backend only; Antigravity practice UI pending. Self-reported recall is not validated mastery. Revision invalidation and deletion apply. |
| Student V4 advanced learning | Source/progress primitives now available without overwriting V1. | Curriculum sequencing, longitudinal evaluation and adaptive mastery remain incomplete; no V4 completion claim. |
| Safe inter-agent knowledge | Authenticated read-only, bounded context with immutable source IDs and explicit no-authority trust label. | Receiver must preserve its own authorization/consent gates. No claim of a fully integrated multi-agent runtime. |
| Isolated OCR / Office | Student dedicated text-PDF/DOCX/EPUB parser retained; API native execution remains disabled. | Scanned OCR and Office-PDF are not implemented in that executor protocol. Do not enable legacy API native paths as a fallback. |
| Knowledge K1–K3 | Existing source/library ownership, index, provenance, versions, citations and proposal-only analyzer reused. | Source coverage/freshness and model entailment have bounded guarantees. See existing tests, not documentation labels alone. |
| Knowledge Refresh / K7 | Existing explicit owner refresh re-fetches through SafeFetcher/robots/budgets and records hash/changes; not rebuilt. | Runner remains process-local, not a durable refresh queue. Granular permission revocation and versioned refresh history are not complete. No autonomous refresh enabled. |
| K4 general-code sandbox | **Not implemented/enabled.** Existing parser accepts a fixed data protocol, not generated programs. Design in EXECUTION_GATES.md. | Dedicated microVM/VM runtime, trusted build chain and adversarial containment evidence required. Missing /dev/kvm and no approved remote executor; no unsafe substitute. |
| K5 Skill Builder | K3 and admin proposals remain non-executable data. | Code generation, isolated tests, signed skill artifacts and installation blocked on verified K4. No fake successful test/status. |
| K6 branch/tests/PR workflow | This candidate itself uses reviewable commits and CI; proposed promotion contract documented. | General app-controlled skill PR workflow not implemented. No unattended git, merge, secret access or deployment. |
| K8 Super Admin | New backend-only capability proposals from owned libraries, bounded immutable snapshots, hash-bound owner review/reject decisions and audit. No execution authority. | Sandbox tests and source improvement blocked on K4/K5/K6; no complete autonomous self-improvement claim. Independent review still required. |
| AI orchestrator | PR21 Gemini/OpenAI/optional Claude chat+embedding adapters, task routing/fallback/budgets; ElevenLabs STT/TTS and existing VoiceStudio interface preserved. | Process-local caps aren't a durable billing ledger; no hard dollar guarantee, live quality or realtime voice implementation. Cloud privacy allowlist per request not implemented. |
| Personal Intelligence / IELTS / Presentation / Office / Admin | Prior routes retained, consent and owner scope preserved; honesty fixes stay in PR21. | Dedicated IELTS voice/scoring incomplete; presentation intake is a deterministic template, not researched AI output. Office PDF/OCR unavailable without reviewed worker integration. |
| Supabase / persistence | Existing private server-only Storage adapter, TLS checks, pgvector, migrations, local durable full profile retained.0019 revokes PUBLIC/anon/authenticated table grants. | Full-profile remote object lifecycle/outbox and cleanup are not yet reviewed; full profile still refuses that storage mode. Backup restore not exercised against a real cloud project. |
| Antigravity integration | Existing frontend untouched; additive MASTER_API_CONTRACT.md published for review. | No external review/acknowledgment received. New backend features have no newly integrated frontend. No connected Antigravity review channel is available; the contract is delivered in the repository. |
| Deployment / $10 / P9 preparation | Existing FULL_OWNER_BETA architecture, future owner guide and benchmark protocol retained; expanded gates below. No services created. | No actual4/8GB VM benchmarks, current vendor/tax quotes or safe two-host architecture certified within $10. No production-ready/full-roadmap verdict. |

Final validation evidence and failures are recorded in VALIDATION.md. Passing CI
cannot convert any unresolved product or containment gate above into completion.
