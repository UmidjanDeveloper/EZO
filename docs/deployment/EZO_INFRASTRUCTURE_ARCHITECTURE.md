# EZO infrastructure architecture (P9 preparation)

This file is based on the code at the integration branch head `518786a`. It states what the
runtime actually needs, which architecture is recommended, and what was validated. It is
**prepared, not deployed.**

## 1. Runtime requirements, read from the code

| Component | Fact in code | Consequence for hosting |
|---|---|---|
| API (`apps/api`, FastAPI, Python 3.13, `uvicorn --workers 1`) | `entrypoint.sh` runs, in order:<br>1. the production preflight;<br>2. `alembic upgrade head`;<br>3. the post-migration database checks;<br>4. HTTP. | **A single instance owns migrations.** No horizontal scaling. |
| Production policy (`deployment.py`) | Requires:<br>- token auth with a token of at least 32 characters;<br>- HTTPS-only exact CORS origins;<br>- `DATABASE_URL` with `sslmode=verify-full` (never port 6543);<br>- a non-privileged database role;<br>- no anon or authenticated grants;<br>- `EZO_STORAGE_DIR` on a **mounted** volume or one containing `.ezo-volume`. | Plain `sslmode=require` and admin roles are refused. |
| Storage | Full profile: **local durable volume only**. Supabase Storage is accepted **only** with `EZO_DEPLOYMENT_PROFILE=free-beta`. | Render or any PaaS needs a paid persistent disk for the full profile. |
| Database | PostgreSQL with `vector` (pgvector). The 21 Alembic revisions are validated on PG16 (CI) and on **Supabase PG 17.6.1.084** (validated today, §4). | Supabase Free caps the database at 500 MB, which Student raw revisions (5 MiB each) fill quickly. |
| Workers | `ezo_api.knowledge.jobs.worker` (stored text, 512 MiB) and `ezo_api.learning.refresh_cli` (K7). Both are refused in free-beta. | They need always-on processes next to the API. |
| Native Student parsing | `ezo_api.student.worker` with a pinned executor image on a **dedicated Docker host**. | A separate host is needed; see EXECUTOR_REQUIREMENTS.md. |
| OCR / LibreOffice | **Disabled** in the production API and absent from its image. | Not provided anywhere yet. **Do not enable.** |
| Web (`apps/web`, Next.js 16) | Reads `EZO_API_URL` **at runtime** and injects it through `/ezo-config`. Refuses non-HTTPS origins in production. Per-request CSP nonce (`proxy.ts`). | No public build-time secret. Validated today (§4). |
| Voice | Turn-by-turn REST through ElevenLabs, OpenAI or VoiceStudio. **No WebSocket or realtime path exists.** | No sticky or WebSocket hosting is needed. |
| AI providers | Gemini, OpenAI and Anthropic adapters. Call counters are process-local. | Spending caps must also be set at each provider (SECRETS_AND_PERMISSIONS.md). |

## 2. Recommended architecture: A (owner VPS primary + separate executor + R2)

```
Owner phone/PC ──HTTPS──> [Primary VPS, x86_64 or arm64, 2 vCPU / 4 GB]
                           Caddy (80/443 only, Let's Encrypt)
                             ├─> web  (Next.js, 384 MiB)
                             └─> api  (FastAPI, 768 MiB) ──┐
                           student-worker (512 MiB) ───────┤ internal network, no Internet route
                           refresh-worker (384 MiB, opt.) ─┤
                           db: PostgreSQL 16 + pgvector ◄──┘ TLS verify-full, role ezo_app
                           volumes: ezo-db, ezo-storage
        nightly: backup.sh ── age-encrypted (owner's public key) ──> Cloudflare R2 (≤10 GB)

[Executor host, later]  dedicated Docker + controller for Student PDF/DOCX/EPUB only
                        (no API keys, no file volume, restricted DB identity over WireGuard)
```

- **The files are in [`deploy/primary/`](../../deploy/primary):**
  - `compose.yml` and the `Caddyfile`;
  - `initdb/10-ezo-app-role.sh` (creates role `ezo_app`, the `vector` extension and a
    `hostssl`-only `pg_hba`);
  - `bootstrap-secrets.sh` (host-local secrets and the database TLS CA);
  - `backup.sh` and `restore-check.sh`;
  - `primary.env.example`.
- **Why this option:**
  - It is the only option that runs the **full** profile, with workers, a durable disk and
    PostgreSQL, near the $10 target.
  - Owner data stays on one host with a matched backup.
  - It keeps the repository's rule that native parsing runs on a separate host.
- **Rejected for the full profile:**
  - Render + Supabase + Vercel: about $34.50 or more per month; see the cost model.
  - A single large VPS that also runs native parsers: this breaks the reviewed isolation
    boundary.

## 3. Option B (Render + Supabase + Vercel): only the reduced "free-beta" demo fits

The repository already contains `deploy/render-free-beta.yaml`:
- Render Free, Docker, Frankfurt, `autoDeployTrigger: off`;
- Supabase Storage and database in one project;
- AI, voice, workers, presentations and native processing all **forced off** by
  `free_beta.py`.

It costs $0, but:
- it is not EZO with AI;
- it cold-starts;
- it needs a free Supabase project slot, and both are in use.

Use it only as a public smoke demo, if at all.

## 4. What was validated today (local, disposable, nothing remote)

| Check | Result |
|---|---|
| `scripts/deploy/validate_supabase_migrations.sh` on `supabase/postgres:17.6.1.084` (the exact image of one existing project): vector enabled in `extensions`, `deploy/supabase-private-beta-role.sql`, migrations **as `ezo_app`** | **PASS.** 49 tables, head `0021`, `alembic check` clean, `ezo_app` not privileged, `pgvector_entries` present, anon/authenticated exposure 0. Storage-schema RLS checks are not covered (they need storage-api). |
| `deploy/primary` database service with the real initdb script and TLS | **PASS.**<br>- `ezo_app` has no superuser or createdb;<br>- `vector` 0.8.7 installed and `ssl=on`;<br>- a plaintext connection is **refused** (`no pg_hba entry … no encryption`);<br>- a wrong hostname is **refused** by `verify-full`. |
| API with `EZO_ENV=production`, full profile, against that database (host venv, because image builds cannot reach Debian or Alpine mirrors from this sandbox) | **PASS.**<br>- preflight rc 0, and an unmounted storage directory is refused;<br>- migrations and post-migration checks pass;<br>- `/api/health` returns 200;<br>- `/api/me` returns 401 without the token and 200 with it;<br>- `/docs` returns 404;<br>- CORS allows `https://ezo.localhost` and rejects other origins;<br>- an Office DOCX is created and downloaded as a valid Word file. |
| Stored-text worker and refresh worker under the same production settings | Both started and stayed running. They were not exercised with real jobs. |
| Web `next start` with `EZO_API_URL=https://api.ezo.localhost` | **PASS.** The CSP includes the API origin and `/ezo-config` injects it. An `http://` origin is refused with an error. |
| `caddy validate` (Caddy 2.11.7) on the Caddyfile | **Valid configuration.** |
| `backup.sh` then `restore-check.sh` | **PASS.**<br>- the archive is age-encrypted and both hash checks pass;<br>- it restores into an empty container with head `0021`;<br>- 1 artifact, 1 user, 1 version and 4 files come back. |
| `docker compose config` for `deploy/primary` | **PASS.** |
| `tests/unit/test_deployment_configs.py` (new, runs in CI) | 6/6 pass. |

**Not validated:**
- A full-image build of the stack and the Caddy ACME flow on a real domain.
- arm64 images.
- Real AI providers.
- The executor host.
- Any remote resource.
