# Student V1 integration contract

Base: `16a4ae96dd4a436a5170c357e3de6222f8ef8136` (merged PRs #11–#16).
Student owns `student/`, `/api/student`, `/student`, its immutable inputs and
processing publications. Personal Intelligence, orchestration, IELTS, Office,
Presentation and global UX remain outside this change.

## Authority and runtime boundaries

All endpoints require normal EZO authentication, including the ASGI guard before
request-body consumption in token mode. Local-owner mode remains local-owner mode;
this PR does not introduce multi-user login. A project must belong to the same user.
Null project means **exact global scope**, not every project. IDs are not credentials.
No HTTP claim/heartbeat/publish endpoint exists. Agent orchestration can request
Student data as the authenticated owner, never as a parser or a queue worker.

Raw API uploads **store bytes only**. Public API native execution remains disabled.
The explicitly operator-started `python -m ezo_api.student.worker` requires PostgreSQL,
a trusted immutable local executor image ID, and `--ack-dedicated-executor-host`.
It must run on a dedicated, reviewed Docker daemon, separate from the API and
untrusted workloads. Do not give the API a Docker socket. No production host was
configured, deployed or approved by this work. Missing/unsupported isolation fails
closed; there is no in-process native fallback. Legacy stored-text jobs retain
their processor version and separate worker.

## HTTP contracts

All UUIDs serialize as strings. The application HTTP exception handler and the shared edge guard normalize errors to
`{"error":{"code":"...","message":"safe description"}}`. Although route code passes
FastAPI `detail` internally, the actual wire contract is the error envelope. Validation
errors use code `validation_error` with bounded location/type/message details.
The Student client also tolerates a standard FastAPI detail envelope for compatibility.
Request models reject unknown fields.

- `GET /api/student/status`: text submission support, raw upload formats,
  separate-worker requirement, API `native_execution: disabled`, and
  `ai_provider_configured`. Configured is not proof that a remote provider is healthy.
- `POST /api/student/uploads?filename=book.pdf&project_id=<optional>`:
  raw binary request body (not multipart), maximum **5 MiB**. PDF/DOCX/EPUB only.
  Fixed signature checked in API; ZIP/XML/native parsing occurs inside executor.
  Returns `JobOut` (201), idempotent by exact user/project/source SHA256.
  Authentication precedes body consumption; scope authorization precedes persistence.
- `POST /api/student/readings`: existing JSON `{text,title,project_id?}` for UTF-8
  text. Existing stored-text processor; not a native-worker shortcut.
- `GET /api/student/library?project_id=&offset=0&limit=30`: exact scope,
  bounded (limit 1..100, offset 0..100000), newest-first `{title,job}` entries.
  Retry generations remain visible for history; this is a job-backed library.
- `GET /api/knowledge/document-jobs/{id}?project_id=`: existing safe job status.
- `POST /api/knowledge/document-jobs/{id}/cancel?project_id=`: existing cancellation.
  Running token is revoked transactionally. Native worker observes this within a
  nominal 250 ms poll plus database/CLI latency and physically removes its container.
- `POST /api/student/readings/{id}/retry?project_id=`: explicit failed/cancelled
  native retry **new generation** (201). Old job/result never overwritten; repeated
  request on a prior generation returns its existing successor. At most three
  generations and three admitted attempts across one document. Completed jobs
  cannot retry. Stored-text terminal retry is not implemented by this endpoint.
- `GET /api/student/readings/{job_id}?project_id=&offset=0&limit=4000`: existing
  `PublicationOut`, SQL text slice, 1..8000 Unicode code points. Global/unclipped
  intersecting spans; past-end returns empty text/spans. Hashes identify original
  source and exact output separately. No invented page numbers.
- `GET /api/student/documents/{id}/structure?project_id=`:
  `{document_id,revision_id,source_sha256,offset_unit:"unicode_codepoints",sections}`.
  Sections carry exact `start,end,page?,heading?,member?`; unknown locations are null.
- `POST /api/student/documents/{id}/semantic-index?project_id=&offset=0`:
  explicit provider-backed **32-chunk maximum batch**, `{indexed,next_offset,revision_id}`.
  Uses K1 embedding/vector abstractions. Repeated batch is an upsert; revision is
  checked again under document lock before index writes. No automatic paid calls
  during parsing. Caller must follow next_offset; keyword retrieval works before it.
- `POST /api/student/documents/{id}/learn`: JSON
  `{kind:"answer"|"summary"|"study_guide"|"quiz", question?:string<=2000,
  project_id?:UUID,section_start?:int,language:"uz"|"en"|"ru"}`.
  Answer uses document-scoped K2 retrieval. Other modes use up to six chunks of the
  selected section (or first six current-revision chunks). These are explicitly
  **excerpt-based**, not full-book coverage. Selected section must exist.
  Response: `{status,text,generated,provider,citations,quiz,scope?,verification?}`.
  `status=insufficient_evidence` returns no generated answer/provider/citations.
  `status=generated` identifies configured provider, `scope=retrieved_excerpts`,
  `verification=source_identity_and_offsets_only`.
  Quiz: `{items:[{question,choices[2..4],answer:<zero-based>,explanation,source}]}`,
  1..5 items; answer range, source IDs and explanation citations are validated.

## Evidence and errors

Citations reuse K2 source metadata: source number, document/revision/chunk IDs,
location, bounded excerpt, and for native Student chunks `extra.start/end`,
`extra.source_sha256`, `extra.offset_unit`. Output is checked against actual current
chunk text and DB source substring. Unknown/missing answer citations fail 502;
this validates provenance, **not factual entailment or pedagogical accuracy**.
Do not label model explanations as quoted facts or automatically correct answers.
No live model was invoked during verification. Provider-less learning returns 503,
never an offline canned answer presented as live AI.

Errors include `not_found` (404), `input_limit`/`unsupported_format`/`invalid_input`
(422), `source_not_ready`, `result_unavailable`, `lease_lost`, `revision_conflict`,
`retry_unavailable`, `attempts_exhausted` (409), `provider_unavailable` (503),
`invalid_model_output` (502). Worker errors expose only fixed safe categories.
Scanned PDFs requiring OCR fail safely; no OCR activation or Office worker added.

## Agent integration

Call these authenticated data APIs; render text/metadata as text, never executable
HTML or tool directives. Sources and generated outputs are untrusted. Student has
no code/tool installation, repository write, secret retrieval, GitHub push or deploy
capability. These outputs confer no action approval on another agent. Existing
owner approval remains required by the owning orchestration layer.

Student-managed raw documents are excluded from legacy K1 startup recovery and direct
ingestion. The legacy reindex endpoint returns 409 `student_managed` before changing
status/index; use the Student job lifecycle instead. The internal boolean metadata
marker `student=true` is reserved for this ownership boundary.

No Antigravity agent registration, tool registry or general chat routing was changed.
No caller should scrape the Student UI or depend on internal worker credentials.
