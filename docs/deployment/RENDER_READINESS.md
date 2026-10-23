# Render readiness (API)

- **Connection:** CONNECTED.
- **Status:** CONFIGURATION PREPARED (existing templates reviewed); **not recommended for the
  full profile**; REQUIRES OWNER APPROVAL.

## Account facts (read-only)

- One workspace.
- One **unrelated** free web service (Oregon) with **auto-deploy on every commit**. It was not
  touched.
- No Postgres and no Key Value instances.

## Templates in the repository

| File | Purpose | Status |
|---|---|---|
| `deploy/render-free-beta.yaml` | Reduced demo: Free plan, Docker, Frankfurt, Supabase database and Storage, `autoDeployTrigger: "off"`, every secret `sync: false` | Reviewed; a policy test passes |
| `deploy/render-paid-reference.yaml` | Full profile on the Standard plan with a 10 GB disk at `/app/storage` | Reference only; about $27.50 per month **before** any worker |

- There is deliberately **no root `render.yaml`**, so Render cannot auto-discover a
  Blueprint. `tests/unit/test_deployment_configs.py` enforces this.
- **Blueprint validation:** Render's schema endpoint and its CLI validation need network or
  login access that this sandbox lacks. The templates were checked against EZO's own policy
  test instead: no auto-deploy, no inline secrets, health path `/api/health`. Run
  `render blueprints validate deploy/render-free-beta.yaml` on the owner's machine before
  importing.

## Why Render does not fit the full profile within $10

1. **Memory.** The API is planned at 768 MiB. Starter (512 MB, $7) is below that. Standard
   (2 GB) costs $25.
2. **Storage.** The full profile refuses remote storage, so a Render disk is needed at
   $0.25/GB. Free services cannot attach disks.
3. **Workers.** The stored-text worker needs a background worker service (at least $7).
4. **Single owner of migrations.** That is fine on one instance. As recalled from Render's
   docs (not re-verified here), a service with an attached disk loses zero-downtime deploys.

## If the owner still chooses Render (free-beta demo)

Health check, restart and logs behave as follows:
- `/api/health` is unauthenticated, and the image `HEALTHCHECK` matches it.
- Render restarts the service on failure.
- Logs are redacted by `ProductionFormatter`.

Network:
- TLS is terminated by Render.
- The database leaves through Supabase's session pooler with `verify-full`.

Rollback:
- Use Render "Rollback" to a previous deploy.
- Migrations only move forward, so restore the database from backup if a schema change must
  be undone.

Approval steps:
1. Pause one Supabase project, or upgrade.
2. Create the Supabase project (see SUPABASE_READINESS.md).
3. Create the Render service from the Blueprint. **Approval needed: this creates a service.**
4. Enter the `sync: false` secrets in the dashboard.
5. Run one manual deploy.
