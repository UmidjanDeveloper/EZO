# Full owner beta — $10/month infrastructure ceiling

Baseline: `c3303d94c128406dfd286168cd9dd02079c61f1a`.
**Deployment verdict: BLOCKED.** This change prepares the existing `full` profile,
missing ElevenLabs integration, bounded provider admission and honest IELTS output.
It does not certify full EZO within $10 or claim an unrun VM/provider benchmark.
No deployment, billing, credential creation or merge was performed by this task.
AI API charges are separate from the $10 infrastructure ceiling.

## Implemented capability and acceptance matrix

`EZO_DEPLOYMENT_PROFILE=full` already exposes all product areas. Super Admin adds
only governance privileges; it does not override tenant ownership, explicit memory
consent, budgets, missing dependencies or native containment. It is not a sandbox
bypass. No subscription can grant this role. There is no complete admin console,
only the implemented governance diagnostic endpoint.

| Area / owning code | Real dependency / acceptance | Status and limitations |
| --- | --- | --- |
| Owner auth / projects / conversations (`auth/local.py`, routes) | Server bearer token; PostgreSQL; wrong token 401 before bodies | Implemented single owner, not public OAuth/signup; frontend token still localStorage |
| Super Admin (`api/routes/governance.py`, `owner_admin.py`) | Existing owner account; explicit offline grant/revoke; normal user 403 | Implemented governance status, not a complete platform management console; no autonomous modification/merge/deploy |
| Personal Intelligence (`personal.py`, `memory/`) | SQL goals/profile/manual facts; automatic capture only with consent | Implemented goals, export/delete and consent; no claim of autonomous personal agent ecosystem |
| Chat / specialized agents (`providers/`, `agents/`) | Gemini/OpenAI adapters already exist; Claude optional; model IDs/account quota must be verified | Streaming/fallback and embeddings implemented; tool/structured-output capabilities are not advertised by these adapters; offline mode says it is offline |
| Student stored text (`knowledge/jobs/`, `student/`) | PG queue and separate stored-text consumer | Implemented durable jobs, retries/fencing, reading structure and exact source offsets |
| Student PDF/DOCX/EPUB (`student/ingestion.py`, `documents/executor/`) | Separate trusted controller on dedicated executor host; immutable image ID and PG access | Existing isolated extraction with 5 MiB inputs; no native parser in API; scanned PDF OCR unsupported; arbitrary large books not accepted |
| Student search/learning (`student/learning.py`, `student/indexing.py`) | Provider/embedding account, authorized immutable revision | Implemented provider-backed excerpt learning and scoped search; not exhaustive book understanding; citations must match actual indexed text; no invented citation fallback |
| IELTS (`routes/ielts.py`, `language/`) | Cue cards/state/text; cloud STT/TTS for turn-based voice | Practice implemented. Confirmed word-count band and constant pronunciation score removed. Evaluation returns null scores and explicit no-assessment notice; no validated IELTS AI examiner or pronunciation assessment implemented |
| Language coach / translation / writing / career / academic | Model router, templates, optional scholarship/search clients | Existing text workflows; live multilingual quality/account access not tested; template output is not proof of AI research |
| Presentation (`presentations/`, route) | Python PPTX renderer, structured content, optional OpenAI/Gemini images | Implemented PPTX/SVG/HTML generation. Intake outline is deterministic/template-based, not evidence-backed AI research. Image model/quota and export fidelity require live acceptance |
| Office / artifact versions (`office/`, `artifacts/`) | Durable owner-scoped file volume, SQL metadata; Python DOCX/XLSX/CSV | Implemented generation/download/version operations. LibreOffice PDF conversion and OCR are unavailable in production API; no unsafe install/fallback added |
| Cloud voice (`voice/`) | OpenAI existing; new ElevenLabs STT/TTS; explicit TTS voice | Turn-by-turn only, no realtime adapter. ElevenLabs default TTS languages en/ru; Uzbek TTS not asserted. STT language hint is not proof of accuracy. Provider retention/voice rights need owner review |
| Images / visual / stories (`visual/`, `story/`) | Existing OpenAI/Gemini image adapters, explicit provider quota | Implemented adapter paths/renderers, not live model quality verification; no local GPU required |
| Knowledge K1–K3 / websites / official sources | Authorized sources, safe fetch, bounded parsers, optional API access | Retrieval/indexing/provenance and proposal-only analyzer implemented; native unsupported paths still fail closed. Terms/access restrictions and official-source authorization remain required |
| Optional Ruflo / developer/browser/video agents | Separate integrations or future implementations | Experimental/absent parts remain incomplete; owner role does not make them functional |

Tests and actual run results: [validation handoff](FULL_OWNER_BETA_VALIDATION.md).
The code/test inventory is authoritative over historical roadmap “done” headings.

## Secure architecture and native concurrency

Candidate primary Linux **x86_64** VPS: web + API + restricted-role PostgreSQL/pgvector
+ stored-text consumer; persistent database and `/app/storage` volumes; TLS reverse
proxy and owner-only VPN/private ingress. No public DB, Docker TCP port or raw app
port. Owner phone accesses VPN then HTTPS; their sub-16 GB computer runs no model,
OCR stack or build. Build reviewed images in CI rather than compiling on a tiny VPS.
An owner-controlled hostname/TLS or reviewed equivalent is required; a new paid
domain is not assumed free. Systemd/Docker limits and log rotation protect host disk.

Native Student uses a **second dedicated executor VM/host**, not the primary API/DB
Docker daemon. Existing controller policy must not be weakened to cohost privileged
Docker control with secrets/services. Parser containers receive data on stdin only:
network none, read-only root, 128 MiB tmpfs, no host mounts/socket/DB/API keys;
768 MiB memory, swap zero, 64 PIDs, <=1 CPU, fixed 25-second root-owned watchdog.
Parser UID10001 has no capabilities; controller verifies effective cgroups and exact
namespace flags. Entire container teardown contains setsid/double-fork descendants.
This is container isolation, not a kernel/VM escape guarantee.

The atomic fixed Docker slot admits **one native document per dedicated daemon**.
Run one controller and retain fencing/cancellation/join/cleanup and independent
watchdog. Do not raise concurrency to fit a benchmark. Admission errors defer without
burning healthy-job retry budgets; uncertain cleanup stops the worker. Raw Student
bytes are immutable PostgreSQL rows (`StudentRawRevision`), not API-local files,
so the dedicated controller needs no artifact-volume mount. Its restricted DB
identity remains sensitive and outside parser containers. Restrict DB ingress to
that host or VPN and verify TLS hostname/CA; no `sslmode=require` substitution.

Legacy K1 Office/image library parsers and Python renderers still run with their
existing limits inside application processes; they are not the Student container
boundary and are not a complete native-library sandbox. Retain their residual
library/resource risks in independent review.

Separate CPU-heavy OCR/Office conversion is **not wired into this executor protocol**.
Making all historical native tools work needs an additional reviewed data-only
job/result protocol and worker implementation, including output integrity, quotas,
lease fencing and hostile fixtures. Installing LibreOffice/Tesseract in the API or
mounting its Docker socket is not an acceptable “full owner” shortcut. This missing
boundary is a precise functional blocker even if more RAM is purchased.

Planning allocations, not measurements: primary 4 GB VM — API 768 MiB, PG 768 MiB,
web 384 MiB, stored-text consumer 512 MiB, remainder OS/cache/TLS/burst reserve.
Primary 8 GB gives additional headroom but does not remove the separate-host rule.
Executor 4 GB — one 768 MiB parser plus controller/daemon/OS and bounded caches.
VoiceStudio/local LLM/GPU models are excluded as optional alternative dependencies;
cloud providers supply the implemented chat/voice/image capabilities. A complete
stack must be sampled on **both hosts**, not just sum nominal container limits.

## Hosting and exact budget decision

Official pricing/offer sources attempted on 2026-10-21:
[Hetzner Cloud](https://www.hetzner.com/cloud/),
[Oracle Free](https://www.oracle.com/cloud/free/),
[Google Cloud Free](https://cloud.google.com/free).
All returned proxy **403**, so no current price, capacity, tax or eligibility is
verified. No card, trial, account or VM was activated. Quotes below are explicitly
budget scenarios, **not actual provider quotations**.

| Option | Fit / operational limitations | Budget verdict |
| --- | --- | --- |
| Affordable x86 VPS | Docker+cgroupv2+durable disk can fit existing design; provider must permit namespaces/seccomp/limits. Include IPv4, backup, egress and VAT. A single VPS does not satisfy dedicated native host rule. | Conditional primary only; exact checkout/tax/FX needed |
| Oracle Always Free | Candidate dedicated executor if capacity, account eligibility and x86/ARM compatibility are verified. Historical A1 allowances are not present entitlements. Reclamation/idle policies, card verification, backup and egress need verification; ARM needs rebuilt/tested images, not an amd64 digest. | $0 executor is unverified; scarce capacity cannot underpin a readiness claim |
| Google Cloud trial | Temporary credits, expiry and billing controls are not a recurring <=$10 production guarantee. No automatic conversion/paid billing authorized. | Not selected as sustainable budget plan; at most separately authorized temporary benchmark environment |
| One 8 GB shared VPS | More memory but API/DB plus privileged native controller on same daemon violates reviewed boundary. | Not an approved isolation shortcut |

All-in monthly formula: `(compute + IPv4 + extra disk + off-host backup + egress +
other recurring charges) × (1 + actual tax rate) + FX/card fees <= $10`.
AI provider bills are tracked separately; free credits do not offset infrastructure.

| Illustrative line item | 4 GB primary scenario | 8 GB primary scenario |
| --- | ---: | ---: |
| Compute incl. adequate local disk (assumption, not quote) | $5.50 | $8.00 |
| IPv4 | $0.60 | $0.60 |
| Extra disk within included capacity | $0.00 | $0.00 |
| Independent encrypted backup allowance | $1.10 | $1.60 |
| Egress within included allowance | $0.00 | $0.00 |
| Subtotal | $7.20 | $10.20 |
| Example 20% tax | $1.44 | $2.04 |
| FX/card reserve | $0.36 | $0.36 |
| Total before a paid executor | **$9.00** | **$12.60** |

Backup cost is an allowance, not a verified off-host product. Provider snapshots
alone do not prove independently restorable DB+files. If disk, egress, retention,
second host or tax exceeds the assumptions, the plan fails the ceiling. No unlimited
bandwidth/free external backup is assumed. Cap retention and estimate raw Student
DB growth (5 MiB/document plus indexed text/vector/WAL/backup overhead).

Smallest viable adjustment: keep $10 and obtain a **verified free dedicated executor**
plus a verified primary/off-host-backup quote; otherwise temporarily leave native
jobs unavailable. To require every native historical capability, approve the missing
worker protocol first, then price/benchmark a second host. If both VMs must be paid,
raise budget by the **actual second-host all-in quote plus any primary overrun**;
there is no honest exact dollar increment without current quotations.

## API usage and secrets

Existing OpenAI/Gemini chat+embedding adapters are retained; optional Claude remains.
A shared process-local model budget now bounds chat/embedding attempts, concurrency,
whole-operation deadlines, input characters, batches and output tokens. Failed calls
consume allowance; fallback uses the same budget. Voice has an independent shared
attempt/concurrency/deadline budget and text/audio byte caps. ElevenLabs HTTP uses
bounded streamed replies, no redirects, fixed HTTPS host, safe error categories and
server-only key. No provider SDK dependency added.

**Not a monetary cap:** counters reset at process restart and after 24 elapsed hours;
replicas/CLI workers have independent counters, SDK internal retries and image/search
calls are outside the model wrapper's admission count. Existing HTTP rate/daily caps
still apply, but provider-side spend limits, key restrictions and billing alerts remain
mandatory. No USD pricing inference or durable cross-process billing ledger is claimed.
Use one API process initially. Do not put keys/tokens/DB URLs into Next.js public vars,
URLs, Git, screenshots or browser provider calls. Explicit voice use sends audio to
third parties; verify vendor retention and permitted voice/model use.

The new ElevenLabs REST contract was checked against upstream Python SDK source
commit `f5d53e09e35717523435cee238ac5cc7f51966fb` (text_to_speech and speech_to_text
raw clients). Tests use MockTransport; **no live paid API request** occurred. Account,
model availability, Uzbek quality and actual invoices still require acceptance.
