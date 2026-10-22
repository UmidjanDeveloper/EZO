# Owner-only free beta: private storage and reduced profile

**Release verdict: BLOCKED pending independent review and live Free-plan/privacy/TLS/restore verification.**
This PR removes the *local-disk architectural dependency* for an explicitly reduced
profile. It does not certify a live deployment or current pricing entitlement.
No service, subscription, production credential or deployment was created.
Base: `d00a1c59e78c9e70c5bf426b2e17f00fcd82b666`; Alembic stays at **0018**.

## Candidate architecture and verified limits

Browser → protected **Vercel Hobby UI** → HTTPS **Render Free Docker API** →
**Supabase Free PostgreSQL + private Storage bucket**. Owner bearer token goes to
EZO API only. Storage bytes pass through authorized API downloads; no public or
signed object URL is returned to the browser. No local file fallback exists.

| Option | Actual code compatibility | Current provider verification |
| --- | --- | --- |
| Render Free | Candidate for one reduced Docker API process. All persistent data uses PostgreSQL/private objects; no mounted disk or background worker is required by this profile. Native processing is not supported. | Official Free docs blocked by environment proxy 403. Historic 512 MB/0.1 CPU, ~15-minute idle sleep and shared ~750 hours/month are planning assumptions, **not verified present entitlements**. Cold starts, hours/egress exhaustion and restart behavior need owner confirmation. |
| Vercel Hobby | Existing Next.js monorepo build, public API origin only. No API/worker runs in Vercel functions. | Current eligibility, limits and owner-only protection on the **production domain** could not be verified (403). Do not deploy a public shell first and protect it later. If the Free account cannot provide private access before release, stop. |
| Supabase Free | PostgreSQL/pgvector 0018 and private Storage REST adapter; dedicated project only. No Supabase Auth integration or browser Data API. | Current quotas, inactivity pause/retention, legacy server credential availability and backups could not be verified (403). Historic 500 MB DB/1 GB object/limited egress are not current contractual promises. |
| Railway/Fly trials | Not selected: expiring credits/card-backed usage are not guaranteed perpetual $0. | No trial or billing account activated. |
| Vercel Python/serverless backend | Not selected: current Docker startup/migration/runtime design and foreground exports are not validated as Vercel functions. | No compatibility or free resource guarantee claimed. |
| Other VM/Spaces/free hosts | No alternative verified against persistence, privacy, billing, reclamation and resource requirements. | No provider is silently substituted. |

Official sources attempted on 2026-10-21: [Render Free](https://render.com/docs/free),
[Supabase pricing](https://supabase.com/pricing),
[Vercel Hobby](https://vercel.com/docs/plans/hobby). All returned proxy 403.
Owner must confirm current offers, quota-exhaustion behavior, inactivity and no paid
fallback before authorizing setup. Alerts do not cap spending. Do not enter a card,
activate trials/add-ons or configure keep-alive traffic to evade inactivity rules.

Storage HTTP routes were additionally checked against Supabase's **actual open-source
Storage API implementation**, not inferred from its SDK name: POST/GET/HEAD object,
DELETE bucket with JSON `prefixes`, bucket metadata, 404 missing/409 duplicate.
This is contract evidence, not a live hosted/account test. REST server-key/gateway
compatibility must still be checked with the approved project; no new key is created
by EZO. See [validation and review handoff](FREE_BETA_STORAGE_VALIDATION.md).

## Enabled and disabled features

| Feature | Reduced-profile behavior |
| --- | --- |
| Owner authentication | Mandatory token, at least 32 characters. No/wrong token rejected before reading bodies; exact HTTPS CORS. Single owner, not public multi-user login. |
| Projects, conversations, manual memory, goals | Owner-scoped PostgreSQL CRUD/export. Automatic memory capture cannot be enabled; new manual facts remain explicit user actions. |
| Text chat | Saved conversation plus an explicit **not-an-AI-answer** offline notice in Uzbek/English/Russian. No AI quota is assumed, no inference is faked, and provider keys are rejected. Natural-language requests cannot dispatch tools or specialized agents. |
| IELTS text practice | Cue cards, persisted Parts 1–3 progression and text answers. No AI/speech assessment or synthesized band score; score fields remain null in this profile. |
| Office | User-authored/template Markdown → DOCX; structured rows → CSV/XLSX. One physical render at a time, including after request cancellation. PDF is disabled, not silently substituted. |
| Generated files | Private owner-authorized list/download/version reads. Office's returned URLs now actually resolve to authorized artifact reads. Artifacts are retained; editing/restoring/deleting is explicitly disabled here. |
| Student / PDF / EPUB / DOCX uploads | Disabled **before body consumption**, including raw-job registration. DOCX output generation is distinct from parsing untrusted DOCX input. |
| Knowledge ingestion/snapshots, learning/sync | Disabled HTTP routes and no startup resume. The adapter implements their shared byte-storage abstraction for future review, but enabling these workflows is outside this profile. |
| Agent tools, native workers, OCR/LibreOffice, speech/images, presentations/research | Disabled. No socket, subprocess-native fallback, worker service, cron, tool installation or self-modification is added. External Student/stored-text CLI workers also refuse this profile. |

`/api/status` supplies `deployment_profile`, `disabled_capabilities` and only general
agent availability. Navigation/banner/PDF controls reflect the profile; the backend
allowlist is authoritative and denies unknown future API paths by default. A UI
change or user preference cannot re-enable a blocked route. Full profile remains the
default and retains the mounted-disk production requirement. Remote storage is
currently permitted only with the reviewed reduced profile.

Application operating limits (not vendor quotas): one owner, one process/replica,
2 SQL connections with zero overflow, 2 concurrent Storage HTTP transfers,
20-second deadline per HTTP transfer including slot wait, no redirects,
5,000,000 bytes/object, 262,144-byte request bodies, 4,000 chat characters,
12,000 Office text characters, at most 2 sheets/200 total rows/2,000 cells,
1,000 characters/cell, 5 chat requests/minute and 10/day, 60 other requests/minute.
`0` is not used: it would disable the existing limiter. In-memory budgets reset
on sleep/restart; paid credentials remain forbidden even after reset. These bounds
are not a sustained-load or 512 MB capacity certification. No host SLA is claimed.

## Storage/security contract and residual risk

- Strict HTTPS `<20-character-project-ref>.supabase.co` origin, validated bucket/key
  syntax, no credentials in URLs, no arbitrary host/redirect access. Custom domains,
  self-hosted endpoints and public/CDN URLs are intentionally unsupported.
- Server-only REST credential with `service_role` access. This is **broad project
  authority**: a dedicated project with no unrelated data is required. It is not a
  bucket-scoped least-privilege credential. Key compromise remains HIGH risk and
  needs independent review; no new signing secret/credential is generated here.
- Database and Storage project identities must match; a non-privileged application
  DB role is required before migrations. Private bucket metadata and bounded bucket file limit checked before object
  operations. Startup round-trips a tiny private probe and deletes it. Production
  also requires RLS on `storage.objects`/`storage.buckets` and rejects client-facing
  policies in this dedicated project. Existing anon/authenticated public-table and
  column checks remain. No anonymous read or public bucket policy should be created.
- Object writes never upsert. Duplicate writes succeed only if existing bytes match;
  different bytes cause failure. Artifact content-addressed SHA256 names are
  verified against exact downloaded bytes; corruption is not accepted as success.
  Successful replies are size bounded. Missing objects
  are distinct from auth/outage/timeout failures; storage failure cannot become a
  successful empty download or a local temporary file. Provider bodies/keys are not
  echoed, and the existing production secret redactor includes the new credential.
- SQL and object storage are **not one atomic transaction**. An object upload followed
  by SQL failure can leave a private orphan. No automatic deletion/GC is implemented.
  Destructive artifact APIs are disabled to avoid partial multi-object deletion
  without a durable cleanup/outbox design. Bucket quota must be monitored; retention
  is not a permanent delete feature. Background cleanup needs separate review.
- Fresh dedicated installation only. There is no automatic migration of an existing
  local file store. Do not point an old database at an empty bucket: metadata alone
  is not a backup. Preserve the old installation, copy exact keys/bytes and verify
  hashes and exports before a separately reviewed migration. Missing bytes return
  errors; they are never silently manufactured.
- Shared kernel/native-worker risks and the previous D4/D6/D7 concerns are not closed
  by this profile. Native execution stays outside it. Container vulnerabilities remain
  visible in the validation report; a green fixable-CVE gate is not zero risk.

## Beginner setup guide — FUTURE approval only

**Do not follow provisioning/deployment steps yet.** First review this PR and resolve
the BLOCKED checks. No paid upgrade is an automatic fallback.

1. **Check the accounts.** Confirm all three services actually offer the required Free
   features today, no payment method/trial/add-on, permitted personal usage, quota
   exhaustion suspends rather than bills, inactivity/retention rules, and private
   frontend access before first deployment. Record non-secret evidence. If any gate
   fails, stop; do not provision a smaller unsafe substitute.
2. **After separate owner authorization: Supabase → New project → Free.** Dedicated
   project, region near the chosen API. Database → Extensions → enable `vector` in
   `extensions`. Disable Data API; EZO does not use it. Apply the reviewed
   [`supabase-private-beta-role.sql`](../deploy/supabase-private-beta-role.sql) as the
   project administrator, then set the role credential privately. Never give the API
   PostgreSQL administrator/superuser privileges. No actual credential belongs here.
3. **Supabase → Storage → New bucket.** ID `ezo-private`, **Public off**,
   maximum file size exactly **5,000,000 bytes**, MIME restriction
   `application/octet-stream` (the API stores bounded binary objects). No anonymous
   or authenticated-client Storage policies. Verify RLS remains enabled. Do not
   create public URLs, expose the bucket via a website, or add browser upload rules.
4. **Database connection.** Use direct PostgreSQL or IPv4-compatible **Session pooler
   5432**, not transaction pooler 6543. App role may require `.PROJECT` suffix;
   verify dashboard format and URL-encode password characters. Require
   `sslmode=verify-full&sslrootcert=system&connect_timeout=10`; if system trust cannot
   verify that endpoint, use its trusted CA file. Never set `require`/`disable` or
   turn off certificate verification. Local tests are not a real Supabase TLS check.
5. **Backend review screen.** The candidate
   [`render-free-beta.yaml`](../deploy/render-free-beta.yaml) selects `plan: free`,
   Docker context/root `apps/api`, Dockerfile `Dockerfile`, port `10000`, health
   `/api/health`, one instance, auto-deploy off, **no disk/worker/pre-deploy job** and
   **no generated secrets**. It is outside default root Blueprint discovery. Confirm
   the review shows $0 before approving anything; if Free cannot meet it, stop.
6. **API environment.** Copy names from
   [`free-beta.env.example`](../deploy/free-beta.env.example), not populated values
   into Git. Set the reviewed PostgreSQL URL, exact frontend HTTPS CORS origin,
   project origin, private bucket and server-only Storage credential. Owner token
   and Storage credential belong only in backend secret settings. Keep **all AI,
   search, speech and GitHub credentials absent** and all listed disable/limit values.
   `EZO_ENV=production`, `EZO_DEPLOYMENT_PROFILE=free-beta`,
   `EZO_STORAGE_PROVIDER=supabase` are required. Do not create a fake `.ezo-volume`.
7. **Startup and migrations.** The image fails closed on auth/TLS/profile errors,
   checks the limited DB role, probes private storage, migrates under the advisory lock to 0018, then checks
   vector table, public grants, Storage RLS/policies before HTTP. Storage failure
   does not select SQLite/local disk. Don't stamp or downgrade to force startup.
8. **Vercel review screen.** Hobby, root `apps/web`, include workspace files outside
   root, pinned pnpm from package.json, existing vercel.json commands. Only public
   `EZO_API_URL=https://<approved-api-origin>` goes in Vercel. No owner token, DB URL,
   Supabase credential or AI key, especially under `NEXT_PUBLIC_*`. Configure and
   verify production-domain owner-only protection **before** a release. Stop if this
   requires a paid feature. Disable unreviewed Git auto-deploys; release the reviewed
   SHA only after explicit approval. Preview protection alone is insufficient.
9. **Owner browser.** Trusted device/profile only; enter token in Settings over HTTPS.
   Current token persistence is localStorage, not HttpOnly session cookies. Shared
   devices/XSS remain risks; no public login or multi-user security claim is made.
   Do not screenshot or paste host secrets into issues. `/ezo-config` exposes only
   the validated API origin, never Storage/DB credentials.
10. **First acceptance.** No/wrong token →401; production docs/schema →404; foreign
    CORS fails. Check free banner/offline notice, create project/manual fact/goal,
    finish IELTS text session (no band), create small DOCX/CSV/XLSX and download the
    returned link. Unsupported native/worker routes must return409. Restart/sleep
    the backend and re-read the same objects and DB entries. Changing a bucket to
    public or adding unsafe policies must refuse startup; never use real private
    data to perform a public-access test. Health200 certifies DB reachability only,
    not cloud storage, backups, provider quotas or privacy protection.

## Backups, rollback and later upgrades

Before private data: prove an encrypted, owner-controlled PostgreSQL export and
private object backup with a manifest of keys/hashes, then restore both into an
isolated approved test destination. Free managed backup/download/retention features
are not assumed. A database dump does not contain Storage object bytes. A phone-only
dashboard and an upload that survived restart do not prove a backup. If a secure
backup/restore route is unavailable at $0, keep launch BLOCKED.

Before release, stop writes, take matched DB/object backups, record prior/new SHAs,
verify 0018 and the image. Roll back application image only if schema compatible;
otherwise forward-fix or separately approved matched restore. Do not blindly downgrade
0018: goals/role data may be deleted. Do not switch back to local storage as rollback
unless all objects are copied/verified onto a genuinely durable disk. Test health,
auth, CORS, consent and byte integrity after recovery. DB pausing and host sleeping
can require manual dashboard recovery; no keep-alive workaround or SLA is promised.

A later paid upgrade may add always-on CPU/RAM, managed backups, durable cleanup and
broader features after explicit budget/review approval. Native ingestion still needs
a separately verified dedicated isolated executor; paying for a web instance does
not establish that isolation. AI keys, new workers, full remote-storage mode and
public launch each require separate authorization. Authorized recurring spend now:
**$0**; no current vendor price quote or live readiness is asserted.
