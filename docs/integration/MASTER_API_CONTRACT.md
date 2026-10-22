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
