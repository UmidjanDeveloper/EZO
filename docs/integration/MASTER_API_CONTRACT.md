# Master candidate backend contract — additive, revision 1

Baseline: integration c3303d94c128406dfd286168cd9dd02079c61f1a, Draft PR21
3ec6cf1cfc7e90588f8c3c2a033a255c3ff70c0b. This is a proposed backend contract for
Antigravity review; no external coordination or approval has been received.
Student V1 endpoints and error envelopes in STUDENT_AGENT_CONTRACT.md remain valid.
No frontend files are owned or modified by this candidate. Migration 0019 is reserved
for Student review cards; other branches must coordinate migration IDs before merge.

## Student review cards (additive)

Authentication, exact user/project scope, normal rate limits and standard error
encoding apply. A null project is global scope only. Every source is untrusted.
Cards reference an immutable revision and an exact, bounded Unicode quote. This
validates provenance, not the truth or instructional quality of an authored answer.

- POST `/api/student/cards`: `{document_id,revision_id,chunk_id,project_id?,front,
  back,quote_start,quote_end}`. Front 1..600, back 1..2000 characters, quote 1..2000
  Unicode code points wholly inside the cited chunk and current source revision.
  Returns 201 card with source quote and global offsets. No model invocation.
- GET `/api/student/cards?project_id=&due_only=true&offset=0&limit=30`: bounded
  list (limit <=100); only current-source cards returned. Removed or revised sources
  invalidate cards for future practice, without altering historical review events.
- POST `/api/student/cards/{id}/review`: `{project_id?,event_id:<UUID>,
  expected_version:<integer>,rating:"again"|"hard"|"good"|"easy"}`. Optimistic
  concurrency; duplicate event ID for identical request returns the original result;
  reusing ID with changed input returns 409. Stale version returns 409. The server
  chooses due time and increments version once, never trusts a client timestamp.
- GET `/api/student/progress?project_id=`: actual card/review counts, due count,
  distinct reviewed cards. Self-reported recall is never labeled examination mastery.
- DELETE `/api/student/cards/{id}?project_id=&confirm=true`: explicit deletion of
  card and its review events, 204. Omitted/false confirmation returns 409.

No agent receives memory consent, tool permission, execution approval, repository
write access or owner authority from a card, source, generated output or citation.

## Integration gates

No new execution endpoint will be published until a separately reviewed general
code sandbox exists. The document parser is not a generated-code sandbox. K3
remains proposal-only. K5/K6/K8 may prepare proposals; proposals cannot authorize
installation, tool execution, secrets, pushes, merges or deployments.

## Grounded synthesis and safe agent context (additive)

`POST /api/student/synthesize` accepts `{document_ids:[UUID] (1..4), project_id?,
question (1..2000), language:uz|en|ru, kind:comparison|concept_graph}`. Comparison
requires at least two distinct, authorized, indexed documents in the exact scope.
Every source is authorized before embedding/provider calls. Up to two retrieved
excerpts per document, at most eight total. Sources without verifiable global
offsets are excluded; missing evidence returns `insufficient_evidence` without a
generated answer. No provider returns 503. Failed source/schema checks return 502.

Comparison output must cite every selected document. Concept graph output has at
most 20 unique nodes and 30 edges; each node/edge carries source number and exact
quote. Unknown nodes, sources, fabricated quotes and unknown fields are rejected.
Nodes' labels and edge relationships are **model interpretations**; quote matching
does not verify entailment. Responses state `scope:retrieved_excerpts` and
`verification:source_identity_and_quotes_only`. This is not whole-book coverage.

`POST /api/student/context` accepts the same selection and returns outbound
LlamaIndex TextNode JSON only, with `trust:untrusted_source_data` and
`action_authority:none`. It never accepts serialized LlamaIndex objects, executable
nodes, loaders, file paths, skills, SQL or pickle. Context transfer neither grants
memory consent nor authorizes tools in a receiving agent. Consumers must keep the
original source/revision/chunk IDs; re-authorize before a later data read.

`POST /api/student/documents/{id}/learn` additionally accepts `kind:flashcards`.
Existing answer/guide/summary/quiz shapes remain. Flashcards include 1..5 proposed
`CardIn` bodies after exact quote and citation checks, plus
`persistence:proposal_only_explicit_save_required`. The caller must obtain an
explicit save action; generation never creates study cards or memory automatically.
Only current, <=2 million character revisions are eligible for new global-offset
features. Legacy chunk offsets are inferred only for an exact unique contiguous
match; repeated/ambiguous or reconstructed chunks are rejected, never guessed.

## Super Admin proposals (review-only)

- POST `/api/admin/governance/improvements`: `{library_id,goal<=1000}`. Strict
  backend `super_admin`, exact owned library, maximum ten learned sources, maximum
  32 KB UTF-8 proposal snapshot. Reuses K3 evidence-graded capability analysis.
  Returns `{id,sha256,status:proposal_only,analysis,...,sandbox_tested:false,
  execution_authorized:false}` and records the immutable snapshot in audit storage.
- GET same path: bounded own proposal snapshots, limit<=50, offset<=100000.
- POST `/{id}/decision`: `{proposal_sha256,decision:request_independent_review|reject,
  confirm:true}`. Wrong hash 409, inaccessible proposal 404, no admin 403. Decision
  is audit logged and grants **no execution, merge or deployment permission**.

There is no execute/install/push/merge/deploy route. Owner review intent is not
independent review, approval to run generated code or approval to merge a PR.
These additive contracts are ready for Antigravity review, not evidence that
Antigravity implemented or approved any frontend integration.


## Additive final-backend candidate contracts (awaiting independent review)

Base ce9b21f; existing contracts unchanged. No frontend edits are required here.

- POST `/api/admin/governance/improvements/{proposal_id}/drafts`: Super Admin,
  same proposal owner, exact `proposal_sha256`, `language:python`, `source`
  <=16384 UTF-8 bytes, `purpose`1..1000; unknown fields422. Returns201 with
  `id`, canonical payload `sha256`, immutable source and static `validation`.
  Static rejection is saved as untrusted data, never run. Wrong hash409;
  absent/foreign proposal404; ordinary/subscription user403.
- GET same path: owned paginated immutable drafts, `limit`1..50 (20 default),
  `offset`0..100000. Response entries `{id,sha256,draft}`. Empty pages return[].
- POST `.../drafts/{draft_id}/decision`: exact `draft_sha256`,
  `decision:request_independent_review|reject`, `confirm:true`. Durable review
  intent only, all execution/merge/deployment flagsfalse; exact parent/owner and
  hash checked. No code execution, installation, git or CI-verification endpoint.
- GET `/api/learning/sources/{source_id}/versions`: authenticated source owner;
  limit1..50/offset0..100000; entries actual finalization audit ID/time, schema
  source-version-v1, content/previous hash, source version/status, complete_fetch,
  bounded document/revision/hash manifest, truncation flag, changed/removed counts.
  Older runs are not backfilled. Missing/foreign/deleted source404, empty page[].
- GET `/api/student/practice-plan`: exact owned nullable `project_id`, `limit`1..20
  (10 default). Metadata-only due recall actions for current source revisions,
  lower recall interval then due/id order. Contains policy, assessment, generated_at,
  items(card/document/revision IDs, original global quote offsets, expected_version,
  due_at, reason), empty_reason. No model or writes; it is not a curriculum or
  mastery measure. Existing card review fences/authorization still apply.


## Eight-upstream / JARVIS foundation (backend candidate; no remote device dispatch)

- POST `/api/jarvis/percentages`: authenticated, default rate limit, explicit
  `method:percent_change|percent_of`,1..50 `pairs` each `{id,previous,current}`,
  ASCII decimal strings (<=18 integer and12 fractional digits, <=32 chars),
  `decimal_places`0..8 default4. No expressions, exponent, float/NaN, unknown fields,
  duplicate pair IDs, guessed method or zero denominator. Returns actual textual
  results, explicit formula/ROUND_HALF_EVEN, caller-input provenance and a durable
  receipt. It does not extract file data, produce PDF, infer recipients or send.
- GET `/api/jarvis/receipts/{id}`: owner-scoped calculation receipt; absent/foreign
  returns404. Schema ezo-execution-receipt-v1 stores tool_call outcome, hashes and
  actual duration only, no financial values, file contents, prompts or guessed
  model token/cost/quality scores. `external_delivery:not_attempted` is literal.
- GET `/api/jarvis/capabilities`: code-registered tool schemas, confirmation flags,
  timeouts and execution_authorized:false. Registration/schema availability does
  not imply configured provider health. Explicit device_features list unmet
  Windows/Chrome/mobile/Office-PDF/Telegram requirements; none is silently enabled.
- POST `/api/jarvis/inspect-plan`: `{nodes:[{id,tool,arguments}],links:[{source,target}]}`,
  <=12 nodes, <=144 links, arguments <=4096 UTF-8 JSON bytes/node. Unique IDs,
  no duplicate/missing/self/cyclic edges. Reuses MissionPlan and actual tool schema;
  fixed read-only planning allowlist intersected with registered tools. Unknown
  arguments, caller approval flags and execution/shell tools rejected422. Returns
  canonical normalized plan hash, status static_inspection_only and no authority.
  It does not query the documents named in arguments or attest their ownership.
  Runtime authorization must run again at any future action boundary.

Companion protocol source: `apps/api/src/ezo_api/companion/protocol.py`.
Only action `file.metadata.list`. Version1 messages bind actor/device/task/root,
request UUID and <=60-second lifetime; Ed25519 domain-separated request/response
signatures and exact request hash. Canonical bytes are UTF-8 JSON, ASCII keys sorted,
compact separators, Unicode preserved, complete normalized schema/default fields.
`size_bytes` and `modified_ns` are decimal **strings**: JavaScript must not round
nanoseconds through Number. Issuance/response clocks tolerate at most5 seconds
of skew; expiry is enforced without grace. No filesystem path, shell, install, message,
file-content-read or general code parameter exists. The standalone Linux module
is configured by the owner with a selected root, manually pinned controller public
key and device private key via inherited FD (never argv/stdout). It has **no remote
pairing/enrollment/API queue yet** and is not loaded by the main API.

Linux metadata implementation uses an owned O_DIRECTORY/O_NOFOLLOW root FD,
nonrecursive <=1000-entry scan, <=50 returned regular-file metadata rows, persistent
private replay journal (<=10000 requests, fail closed on budget), dedicated EZO1
application/schema identity (foreign owner SQLite databases rejected before writes), root/actor/device/
key identity binding across restart and signed actual outcomes. Symlinks, FIFOs,
directories and device nodes are excluded. File IDs are identities, not bearer
read grants. Filenames are untrusted display data and must be escaped by UX.
Sorting uses mtime, not verified download chronology; ties and incomplete scans
must prompt clarification before choosing a file. Two-second scan checks are
cooperative between OS calls, not proof that a stalled filesystem syscall can be
cancelled; parent/controller hard-stop and production-host acceptance remain gates.
This is not K4 general-code isolation. Windows is refused without native handle/
DACL support. Android/iOS/Chrome support must not be inferred from Linux tests.

Antigravity integration remains pending. Do not display a completed voice/file/PDF/
Telegram task from a static plan or arithmetic receipt. No API for remote dispatch,
external sending, grant creation or automatic pairing is implied by these contracts.

### Local companion controls (no new remote API)

Trusted operator CLI now accepts `--cancel-request <uuid>` or `--revoke`, with
the same pinned identity/root/key FD configuration. Cancellation tombstones and
permanent authority revocation survive process restart; final completion is fenced
under a journal write transaction. Wire messages remain v1. Journal upgrades v1→v2
transactionally; old binaries must refuse v2 rather than ignore revocation.
Missing control/replay state is not reset. No automatic retry/re-enable, remote
control ingress or new tool action is introduced. Full semantics and rollback
limits: `docs/master/COMPANION_LIFECYCLE.md`.

### Native mission result truthfulness correction

`NativeOrchestrationProvider` (existing in-process backend module, no new HTTP
mission route) now emits `completed` only if every required step completed.
A rejected required approval with dependent steps skipped ends `cancelled` with
`failure_reason`; other unsuccessful incomplete endings fail. Existing actual
step failures still end `failed`. Result `outputs` retain real partial outputs,
but the top-level non-success summary reports the ending reason rather than the
last successful intermediate step. This intentionally corrects the older test
contract that labelled a rejected action/QA-skipped mission `completed`.
Antigravity must preserve these status distinctions and never render partial
outputs as successful delivery. No execution permissions or enum values added.

### Voice resource enforcement (no schema change)

OpenAI/VoiceStudio now enforce existing audio limits before SDK response buffering,
<=256000-byte transcript/error responses and an operation-wide deadline. Oversize,
compressed or redirect responses fail without returning partial success; provider
fallback remains under existing configuration. Cancellation closes the stream.
No new credential, consent, provider or dollar-cap claim. See
`docs/master/VOICE_RESOURCE_LIMITS.md` for exact bounds and tests.
