# EZO single-owner private beta

This is a deployment preparation, not evidence of a live deployment. Provisioning,
production credentials and the first release require the owner's approval. Never
connect this runbook to production automatically from a pull request.

## Audit of the verified base

Base: `7a27466ec2e2b721be3bf0ed02f6753e481fd7e1` on
`claude/gifted-goodall-bpf01s`. Deployment branch: `feat/private-beta-deploy`.

| Boundary | Existing behavior | Private beta decision |
| --- | --- | --- |
| Frontend | Next.js monorepo; workspace TS packages; runtime `/ezo-config` | Vercel project rooted at `apps/web`, with workspace access; only public API origin reaches browser |
| API | Docker with OCR/LibreOffice and a non-root user; fixed port; shell as PID 1 | Render Docker service; configurable `PORT`; `exec` one Uvicorn worker; fail before HTTP if migrations fail |
| Authentication | Single-owner bearer token exists, but local mode is the default | Preserve it; production startup requires token mode and a 32+ character random token |
| Database | Async psycopg, SQLAlchemy `pool_pre_ping`, Alembic, pgvector | Supabase PostgreSQL via direct/session connection with verified TLS; no transaction pooling |
| Pool size | SQLAlchemy defaults: 5 persistent + 10 overflow connections per process | One API process; budget 15 connections plus migration/maintenance; no autoscaling |
| Migrations | Applied before Uvicorn; no external migration worker | Single-instance, fail-fast startup; backup first, additive migrations, manual release |
| Files | Local storage abstraction; uploads/artifacts reference filesystem keys | Render persistent disk at `/app/storage`; no Supabase Storage integration is claimed |
| Jobs | In-process ingestion/learning; unfinished work resumed at startup | One always-on instance; restarts may interrupt streams; no serverless/scale-to-zero backend |
| CORS | Explicit origins supported, defaults point at localhost | Exact owner frontend HTTPS origins; no wildcard or preview-domain patterns |
| Health | `SELECT 1`, previously HTTP 200 even when degraded | Unauthenticated `/api/health`; HTTP 503 on database failure; no secret details |
| Logs | Audit IDs and operational logs; exception payloads could reach logs | Production formatter redacts configured credentials and withholds exception payloads; no Uvicorn access URLs |
| Debug | Owner traces and API schema available by default | Disable traces and public schema/docs in production |
| OCR/Office | Native Tesseract language packs and LibreOffice in API image | Keep native Docker dependencies and Latin/Cyrillic fonts; avoid Vercel for this work |

Shared-module overlap is limited to `main.py` (startup validation, logging, API docs)
and `api/routes/system.py` (health status). No learning, research, IELTS, SkillForge,
presentation or capability-analysis code is changed. These two startup/health hunks
must be reconciled explicitly if another branch touches the same lines.

## Selected architecture and alternatives

Browser → Vercel UI → **direct HTTPS** → Render API → Supabase PostgreSQL.
The browser sends the existing owner bearer token directly to the API. File uploads,
downloads and streaming chat also go directly to Render, avoiding Vercel function
body-size and execution-time limits. Do not implement a Vercel proxy for these routes.
AI keys and the database URL exist only on the API host.

| Docker host | Trade-off |
| --- | --- |
| **Render (selected)** | Straightforward Docker, TLS, health checks, persistent disk and predictable instance pricing. A disk restricts this design to one instance; deployments have downtime. |
| Railway | Convenient Docker and volumes with usage-based billing. Requires CPU/RAM/spend limits and careful volume/redeploy behavior; monthly cost is less predictable. |
| Fly.io | Flexible Machines, regional volumes and explicit deployment controls. More operational responsibility for volume placement, backups, machine recovery and release coordination. |

Choose Render Standard (roughly 2 GB RAM) initially; OCR and LibreOffice are memory
intensive. Monitor actual peaks; this is not a capacity guarantee. Choose a Supabase
region close to Render Frankfurt or edit the blueprint region before provisioning.

Object storage would enable multiple API instances but would require implementation,
large-file/multipart tests and migration of existing objects. The current local storage
provider is retained on a durable disk for this single-owner beta. Disk durability is
not an off-host backup.

## Configuration boundaries

Use [`deploy/private-beta.env.example`](../deploy/private-beta.env.example). It contains
placeholders only. Do not commit populated copies. Enter values in host settings.

| Location | Inputs |
| --- | --- |
| Render API only | `DATABASE_URL`, `EZO_API_TOKEN`, provider keys, production/auth/CORS/storage controls |
| Vercel | `EZO_API_URL=https://<api-host>`; this is intentionally public |
| Owner's browser Settings | The owner bearer token, entered manually over HTTPS |

Never put keys, database credentials or owner tokens in `NEXT_PUBLIC_*`, Vercel build
arguments, URLs, source code, screenshots or PR logs. `/ezo-config` serves only the
validated API origin and is uncached. A production frontend without a configured URL
returns HTTP 503 for that configuration route rather than silently using localhost.
Explicit HTTP loopback endpoints remain supported for Docker and browser tests.

The existing token is stored in the browser's local storage. It is a full-access owner
credential, not a multi-user login system. Use a trusted browser profile/device; clear
it on shared devices. Rotate by changing the host secret, restarting the API, and
replacing the browser value. Avoid third-party scripts. Use Vercel's deployment
protection for preview deployments; do not grant arbitrary previews production CORS
access. A public UI by itself grants no API access.

## Owner-approved first deployment

1. Review and merge the PR into the integration branch after checks and independent
   review. No automatic merge or production deploy is configured. Record the reviewed
   full commit SHA for both hosts; do not release a moving branch tip accidentally.
2. In Supabase create/select the approved project. Enable `vector` in the database
   Extensions UI (SQL: `CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA extensions;`).
   Ensure the connection role's search path can resolve the extension and has DDL rights
   for EZO's public tables. EZO does not use Supabase Auth/PostgREST; its tables must not
   be exposed through Supabase's Data API. Disable the Data API for this dedicated
   project. As a second layer, migration 0014 revokes every privilege of the `anon` and
   `authenticated` roles on EZO's tables, sequences and functions (also future ones),
   and the post-migration check refuses to start while any such grant exists. Do not use
   this database as a public client API.
3. Copy **Connect → Session pooler** (port 5432; usable from IPv4 hosts), or a reachable
   direct PostgreSQL endpoint. Use the documented `postgres.PROJECT` username for the
   pooler and percent-encode password special characters. Do not use transaction pooling
   on port 6543: psycopg prepared statements and schema management expect sessions.
   Production startup refuses a `DATABASE_URL` on port 6543.
   Set `sslmode=verify-full&sslrootcert=system&connect_timeout=10`. If the endpoint's CA
   is not in system roots, download its trusted CA from Supabase settings, mount it on
   the API host, and set `sslrootcert=/path/to/ca.crt` instead. Never disable verification.
   Production validation rejects SQLite and unverified TLS modes.
4. After approval, create the Render service from `render.yaml`. It defines no automatic
   deploy trigger, one Standard instance and a 10 GB persistent disk. Configure the
   session database URL and exact frontend HTTPS origin. Render can generate the owner
   token; copy it securely to the owner's browser only. Add at least one provider key
   for live AI use; without one the protected API remains honestly offline.
5. Confirm the disk is mounted at **`/app/storage`** and UID 10001 can write it. The
   startup preflight checks writability, not the host's durability guarantees: verify
   the actual host disk attachment in settings. All retained uploads, generated files,
   knowledge source snapshots and versions must be under that path. Do not substitute
   ephemeral container storage. Never attach an empty disk over an existing installation
   without copying and checking its stored objects first. Production startup refuses a
   storage directory that is not a mount point; where the host's disk does not show up
   as one, create the empty file `/app/storage/.ezo-volume` on the persistent disk after
   verifying the attachment yourself.
6. Create the Vercel Next.js project with root **`apps/web`**, enable inclusion of files
   outside the root directory, use the pinned pnpm version from root `package.json`,
   and set `EZO_API_URL` to the actual Render HTTPS origin. The local `vercel.json`
   installs from the workspace root and builds the app. Keep production and preview
   variables separate. No API secret belongs here.
7. Manually release the reviewed commit to Render. Startup validates production policy
   and writable storage (a hosting marker such as `RENDER`, `K_SERVICE`, `FLY_APP_NAME`,
   `RAILWAY_ENVIRONMENT` or `DYNO` without `EZO_ENV=production` is refused, so a missing
   variable can never start local owner mode on the internet), runs `alembic upgrade
   head` under a PostgreSQL advisory lock, checks that `pgvector_entries` exists (when
   `EZO_VECTOR_STORE=pgvector`) and that `anon`/`authenticated` hold no grants, then
   `exec`s Uvicorn on `PORT`
   (default 8000; blueprint 10000). A preflight/migration error exits nonzero and never
   opens HTTP. Keep one service instance and one worker. Do not use a pre-deploy command
   that needs the persistent disk; the disk is attached to the service itself.
8. Release the same reviewed frontend commit to Vercel. Complete the acceptance checks
   below before inviting the owner to use it. Record URLs and release SHA privately.

## Acceptance and operational checks

- API `/api/health`: HTTP 200 and `status=ok,database=ok`. Database failure must be
  HTTP 503. The probe does not certify provider credentials, disk durability or backups.
- API `/api/me`, `/api/chat`, file lists/downloads: no/wrong bearer token yields 401;
  correct owner token succeeds. Production `/docs` and `/openapi.json` return 404.
- Allowlisted origin preflight succeeds; unrelated origin fails. CORS is a browser
  control, not a replacement for token authorization.
- Browser: verify `/ezo-config` has exactly the public API origin, enter the owner token
  in Settings, chat, upload a small document, download a generated artifact and inspect
  the console for mixed-content/CORS errors. Repeat after an API restart to prove the
  same uploaded file and artifact bytes remain available.
- Confirm `vector` is installed and run migration/schema checks before inviting use.
  No provider key means live AI/embeddings remain unverified even when health passes.
- Requests without the correct token get 401 before their body is read, and bodies
  above the upload limit get 413 before they are stored (edge guard). Failed token
  attempts share one global budget (30/minute, then 429); rate limits count only the
  owner's authenticated requests, so strangers cannot use them up, and `/api/health`
  is never limited. Calls that may reach a paid AI provider are capped per day
  (`EZO_RATE_LIMIT_CHAT_PER_DAY`, default 1000).
- The web app sends a nonce Content-Security-Policy (scripts only with the request's
  nonce, connections only to itself and the API origin, no framing). Check the browser
  console for CSP violations after the first deployment.
- Watch RSS, CPU, disk free space, 401/429/5xx rates and provider budgets. Configure
  host alerts and independent HTTPS health monitoring. Keep provider account spend
  caps; the in-memory limits are secondary and reset on restart.

The API intentionally runs as one always-on process. Do not scale replicas/workers:
the rate limiter and background tasks are process-local and the file store is tied to
one disk. Ingestion and learning resume queued/processing records on startup, but
chat streams and document generation may be interrupted by deploys. Do not deploy
while the owner is uploading, generating or synchronizing. Long requests can still
hit host/browser/provider limits; keep beta documents bounded and retry interrupted
foreground work manually. There is no new durable queue or exactly-once claim.

Default trusted forwarded headers are loopback only. Authenticated requests are
limited per owner, not per IP, so a shared proxy IP does not matter for the owner.
Do not set `FORWARDED_ALLOW_IPS=*` without verifying that every ingress overwrites
untrusted client forwarding headers. Never trust headers as owner authentication.

Production logs redact configured secret values and omit exception payloads; SDK
HTTP debug logs and Uvicorn access URLs are disabled. Treat logs as sensitive anyway:
IDs, provider error messages and operational metadata can remain. Restrict access,
set short retention, and never enable debug tracing to diagnose live private files.
Inspect startup/migration failures through the host's restricted logs. Do not paste
database connection errors or populated environment files into issues.

## Backups, release failure and rollback

Before the first real use, prove a restore into an isolated database and separate disk.
Use Supabase's appropriate backup plan plus encrypted off-host exports of both database
and `/app/storage`; host disk snapshots alone are insufficient. Stop writes while
capturing a matched database/file backup, record both backup IDs and the release SHA,
and verify restoring an upload and a versioned artifact. Define retention and recovery
targets with the owner. Never use live owner data in CI.

Before each manual release, pause owner activity, take the matched backup, review new
Alembic revisions and their compatibility with the running code, and record the prior
image/release SHA. Do not run concurrent migrations. A migration failure prevents new
HTTP startup; inspect the revision table and schema before retrying. PostgreSQL DDL is
usually transactional but external operations and future revisions may not be. Do not
blindly stamp, downgrade or rerun a failed data migration.

Roll back the image only if the new schema is compatible with the old code. Otherwise
forward-fix or restore the matched database and files during a maintenance window,
with owner approval. Render disk deployments have downtime and no automatic failover;
an unsuccessful release may leave the service unavailable. Confirm health, owner auth,
file integrity and resumed ingestion after any restart or restore.

## CI and estimates

Existing GitHub Actions remains validation-only: Python lint/format/mypy, SQLite and
PostgreSQL suites, migration drift, frontend lint/types/tests/build/E2E and Docker
build/smoke tests. Deployment changes add startup-policy, auth/CORS/health, browser
runtime-config and persistent-volume smoke coverage. No production credential or paid
resource is required by CI. Do not approve deployment while unexplained checks fail.

**Monthly estimates, not quotes:** Render Standard about $25 plus 10 GB disk about
$2.50; Supabase Pro about $25; Vercel Hobby $0 where its personal/non-commercial terms
apply, or Pro about $20 per seat. Expected starting total about **$52.50–$72.50/month**,
excluding AI, bandwidth/egress, object backups, taxes and usage overages. Check current
prices and terms before approval: [Render](https://render.com/pricing),
[Supabase](https://supabase.com/pricing), [Vercel](https://vercel.com/pricing).

References: [Render disks](https://render.com/docs/disks),
[Blueprint specification](https://render.com/docs/blueprint-spec),
[Supabase connection modes](https://supabase.com/docs/guides/database/connecting-to-postgres),
[SSL](https://supabase.com/docs/guides/platform/ssl-enforcement),
[Vercel monorepos](https://vercel.com/docs/monorepos).

Actual live Supabase TLS/extension access, host volume ownership/durability, provider
credentials, Vercel project settings and backup restoration must be verified on the
approved infrastructure. Passing local tests does not establish any of those outcomes.
