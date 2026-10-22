# Mandatory upstream implementation matrix — eight repositories

Upstream integration landed through externally merged PR25 at
`cd9bbd0633022885ef429929a52228146dc51408` (head6ab4a95, identical source tree).
Its earlier base4ca3566/PR24 work is preserved. Codex did not merge PR24/25 or deploy.
Current continuation: `feat/knowledge-refresh-governance`, based on cd9bbd0.
Knowledge recovery, per-document publication serialization, input integrity and
local atomic storage prerequisites are documented in KNOWLEDGE_REFRESH_GOVERNANCE.md.
They do not complete K7 or waive any upstream gate. Independent-review evidence
is not inferred from an external owner merge.

All eight are binding requirements. Review/reference is not implementation.
Status below covers the exact named feature; no row certifies whole-framework or
end-to-end owner desktop automation. Continuation changes remain review candidates.
Antigravity owns UI, Chrome extension and companion UX; no new UI files are edited.
Source paths in the table are relative to `apps/api/src/ezo_api/`; test paths are
relative to `apps/api/tests/` unless stated otherwise. All four new license notices
are under `docs/third-party/`. Runtime copies (plus the existing LlamaIndex notice)
ship in `apps/api/src/ezo_api/_third_party/` and are checked by
`tests/unit/test_runtime_notices.py` and actual wheel/image probes.

| Upstream feature | EZO implementation / source files | Working test evidence | License | Status and precise limits |
|---|---|---|---|---|
| **LlamaIndex** — typed, provenance-preserving knowledge nodes | Existing `student/synthesis.py` (`llama_nodes`, context), `student/provenance.py`, routes `student_study.py`; pinned core0.14.25 TextNode interchange for real owned excerpts | `tests/integration/test_student_synthesis.py`: real installed TextNode interchange, current owned source/quote validation, comparison/graph model-schema rejection. Part of retained-upstreams.xml run | MIT; LLAMAINDEX_LICENSE.txt | **PARTIAL IMPLEMENTED**. Real context interchange; EZO K2 does retrieval. Not upstream agent/query-engine integration; no whole-book entailment or live model quality proof. |
| **Ruflo** — non-widening typed capability restriction | Python adaptation `orchestration/planning_policy.py`: intersection of tools, earliest expiry, exact actor. Used by `orchestration/tool_plan.py` to restrict graph inspection to EZO's registered, explicitly inspectable tools | `test_jarvis_foundation.py::test_restriction_cannot_widen_tools_actor_or_deadline`; HTTP malicious tool/authority/argument tests in `test_jarvis_api.py` | MIT; RUFLO_LICENSE.txt; source pin below | **PARTIAL IMPLEMENTED**. Actual inspector admission, not execution grants. External Ruflo CLI/MCP remains disabled: known bridge RCE advisory, no reviewed isolated runner or restricted adapter evidence. Alternative is bounded native EZO coordination, not unrestricted agent spawning. |
| **VoiceStudio** — separate OpenAI-compatible STT/TTS HTTP service | Existing `voice/openai_audio.py`, `voice/service.py`; new `voice/http_limits.py` bounds actual SDK response streams/deadlines; settings VOICESTUDIO_URL/key/voice; no upstream source in EZO | `test_voice.py::test_voicestudio_wire_format_with_real_sdk` asserts actual SDK HTTP wire requests with MockTransport. Provider fallback/API tests retained; `test_voice_http_limits.py` verifies real SDK chunk limits, deadline and cancellation/closure. This is **not** a live VoiceStudio engine test | Upstream AGPL-3.0-only; HTTP integration contains no copied AGPL code; engine/model terms separate | **PARTIAL IMPLEMENTED** adapter. No running VoiceStudio model/service or Uzbek acoustic quality test available. Copying needs explicit AGPL compliance decision; weights may have noncommercial/additional terms. Existing OpenAI/ElevenLabs remain alternatives; no paid calls made. |
| **APEX-UI** — dashboard/navigation/interface patterns | PR23 inherited AdminPage/StudentPage remain intact. New backend capabilities/receipts/inspection contracts in `api/routes/jarvis.py` are published for Antigravity; Codex does not claim backend JSON is an APEX UI port | Prior full production-browser suite43pass includes Admin/IELTS/Office; this proves existing UI behavior, **not** provenance of an APEX component port | MIT upstream | **PENDING ANTIGRAVITY** for selected reusable UI components, license attribution and browser evidence. No technical reason to exclude UI wholesale; ownership/coordination is the actual boundary. No new frontend copying by Codex. |
| **REA** — explicit prerequisite inventory; missing native authority must not become support | `orchestration/planning_policy.py::availability`, `api/routes/jarvis.py::capabilities`; `companion/metadata.py` refuses Windows instead of equating pathname no-follow with Windows handle authority. POSIX root FD/identity fences used for the supported Linux operation | Missing-prerequisite unit test, capabilities HTTP test, real symlink/FIFO/root-rename/restart/foreign-journal tests in `test_companion_metadata.py` | MIT root; REA_LICENSE.txt; no debugger/capture binaries copied | **PARTIAL ADAPTED** governance/availability approach. No REA reverse-engineering engine installed. Native Windows handles/DACL and authorized RE sessions require their own implementation and real-device tests; Linux test is not Windows evidence. |
| **Supabase** — private object lifecycle via authenticated REST and PostgreSQL/pgvector | Existing `storage/supabase.py`, `storage/__init__.py`, deployment startup/limited DB role checks. Fixed origin/private bucket, no redirects/public URLs/local fallback, bounded immutable objects | `test_supabase_storage.py` HTTP contract/negative tests; full PostgreSQL/pgvector and migration suites at b7b8b09 passed. No live Supabase project used | Apache-2.0 root; no whole stack vendored | **PARTIAL IMPLEMENTED**. Reduced profile adapter works under its contract; full profile still refuses remote storage pending SQL/object outbox/lifecycle review. No real cloud backup/restore or RLS dashboard drill. Alternative full profile requires durable local storage, not ephemeral fallback. |
| **Microsoft JARVIS** — EasyTool-style instruction cards/arithmetic; TaskBench-style tool graphs | `tools/percentage.py`, registration in `services.py`; `api/routes/jarvis.py`: actual percentages, registry-derived cards and graph inspection; `orchestration/tool_plan.py` reuses existing MissionPlan DAG validation | Decimal edge cases and actual HTTP results; graph cycles/missing nodes/unknown tools/forged approval tests. `foundation.xml`/`combined.xml`; no upstream benchmark dataset or claimed intelligence score | Root MIT (JARVIS_LICENSE.txt); HuggingGPT/TaskBench README badges say Apache-2.0: component-license discrepancy recorded, no dataset/source copied | **PARTIAL ADAPTED FUNCTIONALITY**. Real bounded math and static plans, no downloaded model/tool executor. No JARVIS desktop control exists to import. No voice-to-Windows-to-PDF-to-Telegram completion claim. |
| **OpenJarvis** — typed tool interfaces, trace outcomes, local-first fixed operations | `tools/percentage.py` typed tool; `api/routes/jarvis.py` owner-scoped durable metadata-only receipts; `companion/protocol.py` canonical signed task/device/root messages; `companion/metadata.py` separate fixed-operation Linux CLI, replay journal, root/key identity binding and local durable cancellation/revocation | `test_jarvis_api.py` real persisted receipt/ownership checks; `test_companion_metadata.py` real files and separate subprocess with ephemeral key FD, Ed25519 forgery/deadline/scope/replay/cancellation/root replacement, exact-nanosecond/clock-skew/foreign-journal tests; real operator subprocess controls, crash fencing and v1→v2 journal upgrade. No filesystem or OS mocks | Apache-2.0; OPENJARVIS_LICENSE.txt. Selected interfaces/trace concepts adapted; no upstream runtime installed | **PARTIAL WORKING LINUX COMPANION CORE**. Manual key pinning/configuration only; remote enrollment/pairing UI/API, durable multi-step queue, Windows/Chrome/mobile, Office/PDF and Telegram remain unfinished. No local model required. Full-framework package would add unrelated telemetry/GPU/data dependencies; no unrestricted shell/REPL/installer/self-improvement imported. |

## Exact inspected source pins and modules

Previous six pins, code/license/security review and exclusions are in UPSTREAM_REVIEW.md.
New inspection (read-only git objects, no upstream scripts or binaries executed):

- Microsoft JARVIS `7624cf388b47334ff8a0868e7d862dde18cfda86`: root LICENSE/SECURITY,
  HuggingGPT README and server/awesome_chat.py, EasyTool README/util/data_process.py
  and FuncQA math.py, TaskBench README/evaluate.py/tool-graph dataset schema.
  Float rounding, network/model downloader, generated tool code, installers and
  dataset imports are excluded. TaskBench/HuggingGPT Apache badges conflict with
  root MIT; no copying of their implementation/data is used to bypass that question.
- OpenJarvis `8f81c024608bacaefc551761196eeb556ab5631e`: Apache LICENSE, pyproject,
  architecture overview/security, agents/scheduler.py, tools/_stubs.py, core/types.py,
  traces/collector.py and store.py, skills/types.py, evals/skill_benchmark.py,
  engine/cloud.py, frontend/src-tauri config/capabilities, desktop workflow and
  deploy/windows/install.ps1. Desktop manifest version1.0.1 is not proof of a
  runtime package release. Its scheduler's in-memory thread is not a durable EZO
  refresh queue. Python thread cancellation isn't containment. Rich traces store
  raw content upstream; EZO's new receipt stores hashes/metadata instead.
- Ruflo port source: `v3/@claude-flow/guidance/src/capabilities.ts` at
  `5d99b57e7862c0623cf26e0c152dff60e3b50346`. No CLI/MCP loaded.
- REA adaptation references: `src/application/CapabilityInventory.ts`,
  `CapabilityClientRequirements.ts`, `WindowsCapabilities.ts` at
  `c8ed32853881b08aa83459d4da55a28a4e09b0c8`. No tool execution/capture component copied.

## Reproducible working examples (no production credentials)

Authenticated local API, offline mode:

```http
POST /api/jarvis/percentages
Content-Type: application/json

{"method":"percent_change","pairs":[{"id":"income","previous":"100","current":"125"}]}
```

Returns actual `25.0000`, formula/rounding/provenance and a persisted owner-only
receipt. It does not claim these numbers came from a file. Omitting method or
using a zero base returns422; no guessed comparison method.

`GET /api/jarvis/capabilities` returns actual registered schemas plus explicit
missing device requirements. `POST /api/jarvis/inspect-plan` validates <=12 typed
nodes/edges against MissionPlan and the restricted registry. No action is run,
no permission granted and no caller-supplied approval accepted.

Real Linux companion regression command:

```sh
cd apps/api
.venv/bin/python -m pytest -q tests/integration/test_companion_metadata.py
```

Creates only temporary owned files and ephemeral test keys, launches the actual
companion module in a separate process, checks signatures, never reads file bodies
and verifies persistent replay/root binding. This is working Linux code, not a
mocked Windows/phone/Telegram acceptance scenario. Host evidence stays separate.

## Reference owner scenario — BLOCKED

Uzbek voice accuracy, real Windows Downloads ordering/handle authority, two-file
extraction/comparison, isolated Office-to-PDF output verification, recipient
resolution, scoped/revocable send approval and real Telegram test-account delivery
are not demonstrated. The pure arithmetic and Linux metadata core do not satisfy
that end-to-end scenario. Never turn any exclusion into a fake completion receipt.
P0–P9 and the earlier master acceptance gates remain active; no merge/deploy,
paid service activation, production credential creation or billing occurred.

Local revocation/cancellation lifecycle and rollback contract: COMPANION_LIFECYCLE.md.
Remote enrollment/revocation UX and control-plane remain unfinished; local controls
are not claimed as a remote pairing implementation.
