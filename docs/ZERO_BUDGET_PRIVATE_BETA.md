> **Follow-up implementation:** [Remote storage + reduced free-beta profile](FREE_BETA_STORAGE_PROFILE.md).
> This is the historical pre-adapter assessment; no deployment is authorized.

# Owner-only private beta: zero-budget readiness

**Decision: BLOCKED for a complete hosted EZO beta.** Preparation only. No public
launch, provisioning, subscription, secret creation, deployment or merge is authorized.
Base audited: `6e610b20627d591a8be83dad7fed6b79ccc7beb0` (merged Student V1 and
Personal Intelligence/Agent Ecosystem, migration head 0018). This supersedes the
paid and now partly stale deployment guides. Validation evidence is recorded in
[the readiness report](ZERO_BUDGET_VALIDATION.md).

## What $0 can and cannot provide

Target: browser → Vercel Hobby Next.js → HTTPS API → Supabase Free PostgreSQL.
**There is no verified, compatible all-free API/storage/worker host for the current
application.** Do not deploy a frontend against a pretend API or tell the owner the
whole product is usable. An unconnected frontend is a shell, not an offline backend.
Supabase Storage is not implemented by EZO's storage provider.

| Component | Compatibility and decision |
| --- | --- |
| Vercel Hobby | Next.js frontend is structurally compatible; root `apps/web`, workspace install via `vercel.json`. Personal/non-commercial eligibility and owner-only protection for the actual production domain must be checked before any release. No API/worker execution here. |
| Supabase Free | PostgreSQL/pgvector are structurally compatible. A real Free project, session TLS, role privileges, capacity, pausing and restore have not been tested. It does not provide EZO's local filesystem. |
| Render Free | Rejected for current production API: ephemeral filesystem cannot retain uploads, artifact versions and knowledge snapshots. Production `check_storage()` refuses an ordinary container layer. A marker file cannot make it durable. Sleeping/restarts also interrupt foreground work and process-local tasks/limits. |
| Render isolated native worker | Unsupported architecture: EZO requires a separately verified dedicated Docker daemon/cgroup-v2 host, immutable image and namespace teardown. A managed web service does not establish those controls. Never mount a daemon socket into the API. |
| Other free backends | No alternative verified against durable filesystem + Docker + memory + worker + privacy requirements. Trials, credits, payment-card-backed usage and self-hosting on new hardware are not guaranteed $0 hosting. No substitute is selected. |
| Existing owner computer | Local development/offline use is possible with existing hardware/storage, not an approved remotely hosted private beta; electricity, uptime, backups and secure ingress remain owner responsibilities. No public tunnel is configured. |

The old paid root `render.yaml` has been moved to
[`deploy/render-paid-reference.yaml`](../deploy/render-paid-reference.yaml), outside
Render's default root Blueprint discovery path. It remains an explicitly **paid,
not authorized** reference; importing it manually can incur charges. It is not a
free-tier recipe. No disk checks or authentication have been relaxed.

## Current tariff verification and billing risks

On **2026-10-21** the environment proxy returned HTTP 403 for the official Render,
Supabase and Vercel documentation/pricing hosts. Consequently **current Free-tier
availability, exact quotas and pricing have not been independently verified**.
Do not interpret older figures below as present contractual entitlements.

| Service | Previously published planning limits — must recheck in dashboard |
| --- | --- |
| Render Free web | Historically 512 MB RAM, 0.1 CPU, sleep after about 15 minutes idle, shared 750 free instance-hours/workspace/month; cold starts and ephemeral files; no free persistent disks or standalone background workers. Even if all are still offered, disk incompatibility blocks EZO. |
| Supabase Free | Historically 500 MB database, 1 GB object storage, limited egress, inactivity pausing after about a week and no downloadable managed daily backups. Object quota is unusable by EZO until a reviewed storage adapter exists. Confirm present pause, retention and recovery rules. |
| Vercel Hobby | Historically personal/non-commercial use, capped compute/build/bandwidth; exact build duration, function and protection limits vary. Hobby's production-domain protection is not assumed equivalent to paid password/team controls. |

Owner must verify these live sources before a future approved provisioning step:
[Render Free](https://render.com/docs/free), [disks](https://render.com/docs/disks),
[pricing](https://render.com/pricing), [Supabase pricing](https://supabase.com/pricing),
[pausing](https://supabase.com/docs/guides/platform/going-into-prod),
[backups](https://supabase.com/docs/guides/platform/backups),
[Vercel Hobby](https://vercel.com/docs/plans/hobby),
[deployment protection](https://vercel.com/docs/deployment-protection).

Do not enter a payment method, enable a trial/upgrade, attach paid disks, enable
usage-based add-ons or configure AI billing to make this plan appear feasible.
Check that quota exhaustion suspends service rather than authorizing charges, and
that account/team defaults do not select paid plans. Alerts are not spending caps.
Do not add fake keep-alive traffic to defeat inactivity policies. A free project can
pause or disappear; storage quotas do not constitute a backup or uptime guarantee.

## Feature truth table

These describe implemented behavior **on a compatible backend**, not functionality
available from a standalone Vercel deployment. With no compatible API all protected
features are unavailable remotely.

| Feature | No-provider behavior on a durable backend | Current zero-budget hosted status |
| --- | --- | --- |
| Owner token, history, projects, goals, manual memory CRUD/export | Database operations work without an LLM. Memory capture requires both `memory_consent` and `auto_memory`; leave both off initially. Revoking consent is not deletion; explicitly delete/export as needed. | Blocked by API host |
| Chat/router | Honest offline/template responses; no live reasoning or model quality claim | Blocked; frontend alone is not offline chat |
| Student text reading/citations | Authorized UTF-8 text; durable jobs require an explicitly running stored-text worker. API startup does not run that worker. Keyword retrieval works; semantic indexing/learning require a provider. | Worker/API unavailable |
| Student PDF/EPUB/DOCX | Raw-byte registration is implemented, but extraction requires the separate isolated native worker. No API-local parser fallback. Upload acceptance does not mean processing is available. | Disabled operationally: do not submit raw jobs, do not run native worker; API status says native execution disabled |
| Summaries, quizzes, explanations, semantic search | Without providers: unavailable/explicit errors, never fabricated AI success | Unavailable |
| IELTS | Cue cards, session state and text practice are deterministic. The merged session-completion route calculates word-count-based band estimates and a fixed pronunciation baseline (6.0); these are heuristics, not validated language or speech assessment. Other coaching paths can require a model. | API unavailable; no paid speech providers |
| Presentations | Deterministic outline/template fallback and Python PPTX building exist; no live AI authoring/images without providers | API and durable artifacts unavailable |
| Office | Structured content → DOCX/XLSX/CSV/PPTX export can run without an LLM. Generation differs from parsing untrusted native uploads. PDF conversion/LibreOffice/OCR are not included in production API. | API/storage unavailable; native conversion disabled |
| Agents/governance | Routing is not permission to install tools, change source, access secrets or deploy. K3 remains proposal-only; admin role checks remain server-side. | No autonomous actions enabled |

No free AI quota is assumed. **Do not configure any AI credentials**, including
OpenAI, Anthropic, Gemini, Tavily or VoiceStudio, even if a vendor advertises credits.
`EZO_RATE_LIMIT_CHAT_PER_DAY=0` disables the limiter; it does **not** prohibit spending.
The example keeps small positive limits and no provider keys. Local test model
providers are fixtures, not a hosted free inference service.

## Supabase database preparation (future approval only)

1. Use a dedicated Free project, not a shared production database. Choose the same
   region as the eventual API. Enable `vector` in schema `extensions`. EZO does not
   use Supabase Auth or browser Data API access: disable Data API for this project.
2. Review [`supabase-private-beta-role.sql`](../deploy/supabase-private-beta-role.sql).
   `ezo_app` is LOGIN, NOSUPERUSER, NOCREATEDB, NOCREATEROLE, NOREPLICATION,
   NOBYPASSRLS, connection limit 20, with DDL only on its own public-schema objects.
   Set credentials only after approval in a protected dashboard. Do not use the
   project administrator/service-role key in the browser or API.
3. API `DATABASE_URL`: direct endpoint or **session pooler port 5432**, not transaction
   pooler 6543. Pooler username usually includes `.PROJECT`; confirm actual format.
   Percent-encode password characters. Require `sslmode=verify-full`, trusted CA
   (`sslrootcert=system` only if that endpoint chains to system trust), and
   `connect_timeout=10`. No certificate-verification bypass.
4. Startup validates configuration and durable storage **before** migrations, takes
   the migration advisory lock, upgrades to 0018, then checks vector table and
   effective anon/authenticated table/column privileges before opening HTTP.
   Revisions 0014/0015 revoke exposure and set default privileges for the migration
   role; 0017 adds private raw revisions; 0018 adds user roles and personal goals.
   Validate new-table ACLs after 0018 as well. No database RLS tenant-isolation claim:
   owner scoping is enforced in application queries; token mode is single owner.
5. Default SQLAlchemy pool: 5 + 10 overflow per process. Keep one API process/replica;
   budget worker and migration connections separately within actual Free quotas.
   Do not route migrations through transaction pooling to stretch a quota.
6. Free managed backup availability is not assumed. Before private data, perform an
   encrypted owner-held PostgreSQL export **and matched file-store backup**, and
   restore both into disposable storage. A phone-only dashboard is insufficient
   evidence of a usable restore process. Define retention and loss tolerance first.

Proposed conservative beta operating budgets, **not provider entitlements**: one
owner, 5 MB maximum uploads, stop new ingestion around 250 MB total DB usage (leave
migration/index headroom if the historical 500 MB cap applies), no raw native uploads,
no autonomous sync, 5 chat requests/minute, 10/day, 60 other requests/minute. These
are configuration/operator limits, not a hard database quota implementation. A
512 MB local smoke test is not a capacity guarantee for concurrent exports, long
texts or recovery; no realistic sustained-load benchmark establishes Free fit. Jobs,
text/vectors/indexes and revision history also consume database space. The existing
native executor itself needs 768 MB and up to 128 MB tmpfs plus its controller;
a historically 512 MB free web instance is not an adequate native-worker host.

## Phone-friendly owner checklist

**Now: review only. Do not create services.**

1. Review this PR, validation and open risks. Do not merge until independent review
   and explicit owner approval. No full hosted beta launch is presently approved.
2. Open the three official plan pages. Confirm Free availability, no payment method,
   usage-stop behavior, inactivity/retention, private-project eligibility and access
   protection for the exact production domain. Record findings without credentials.
3. Resolve the backend gate in a separate approved task: either a genuinely free,
   durable host with acceptable resources and backups, or a reviewed remote storage
   adapter plus an intentionally reduced deployment profile. Supabase Storage is
   not a drop-in environment variable. Do not create `.ezo-volume` on temporary disk.
4. Resolve the separate Student worker gate. Until then do not upload PDF/EPUB/DOCX
   for processing. Do not promise a paid Render web/disk upgrade solves isolation.
5. Only after a viable plan and new owner authorization: Supabase dashboard → Free
   project → Extensions → vector; disable Data API; apply reviewed limited-role SQL;
   verify TLS/migrations/ACLs/backups as above. Never paste credentials into a PR.
6. Eventual API settings: Docker context `apps/api`, Dockerfile `Dockerfile`, one
   process, port `10000`, health `/api/health`, **auto deploy off**; a real writable
   durable path `/app/storage` owned by UID 10001 is mandatory. Copy names from
   [`private-beta.env.example`](../deploy/private-beta.env.example). Set
   `EZO_ENV=production`, token auth (32+ characters), debug false, exact frontend
   HTTPS CORS origin, verified PostgreSQL URL, pgvector. Keep all provider keys
   absent, OCR/converter/image/voice/search disabled. This is not a Render Free recipe.
7. Eventual Vercel settings: Hobby, root `apps/web`, include workspace files outside
   root, pinned pnpm from root package.json; existing `vercel.json` installs from
   monorepo root. Set only `EZO_API_URL=https://<approved-api-host>` there. Deploy
   reviewed SHA manually only after owner-only protection is configured for the
   production URL; prevent Git integration from deploying unreviewed pushes. If
   protection cannot be established before first deploy, stop. Then confirm an
   incognito visit cannot access the UI.
   If Hobby cannot protect the production URL for this owner, stop; do not buy an
   add-on or label a public shell private. Do not configure a fabricated API origin.
8. Owner token goes only in API secret settings and trusted browser Settings. Current
   frontend uses localStorage: shared-device/XSS risk remains. No API token, database
   URL or model credential in `NEXT_PUBLIC_*`, Vercel env, URLs, screenshots or logs.
   No secret-bearing proxy is introduced; browser calls API directly over HTTPS.
9. First approved acceptance: health 200; no/wrong token 401 on new workspaces before
   body parsing; docs/schema 404; foreign CORS rejected; offline state explicit;
   memory consent off; safe Office generation/re-download after restart; matching
   DB/files restored successfully. Repeat mobile flows. Native jobs remain disabled.

## Rollback and later paid path

Before a release, stop writes and take matched encrypted DB/files backups, record
reviewed old/new image SHAs and migration revisions. Failed preflight must never be
bypassed. If schema is backward compatible, manually restore the prior application
release; otherwise forward-fix or owner-authorized matched restore. Do not blindly
run Alembic downgrade: it may delete new goals/raw revisions. Recheck auth, health,
CORS and bytes after restore. Paused/free projects can require manual recovery;
there is no verified SLA or zero-downtime guarantee.

A later separately approved paid path can add a durable single-instance API disk,
managed backups and adequate memory, while preserving offline/no-key defaults.
The isolated native worker still requires a separately reviewed dedicated executor
host or authenticated remote executor architecture. A storage adapter, durable
worker lifecycle, provider budget enforcement and live restore are distinct reviews.
No current price quote is verified; obtain exact dashboard totals and explicit
spending approval before any upgrade. The present authorized recurring spend is **$0**.
