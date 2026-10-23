# Supabase readiness

- **Connection:** CONNECTED.
- **Status:** VERIFIED for migration compatibility. CONFIGURATION PREPARED. **REQUIRES OWNER
  APPROVAL** to create anything.

## Role of Supabase in the recommended plan

- **Option A (recommended) does not need Supabase.** PostgreSQL runs on the primary host and
  backups go to R2.
- **Supabase is relevant only in two cases:**
  1. the reduced free-beta demo (`deploy/render-free-beta.yaml`), which keeps the database
     and Storage in one project;
  2. a later move to managed Postgres, which needs a paid plan for backups and no pausing.

## Account facts (read-only, today)

- The organization is on the Free plan.
- It has 4 unrelated projects; 2 are active, which is the maximum for Free.
- No EZO project exists.
- **Prerequisite for any EZO project on Free:** pause one active project, or upgrade the
  organization. This is an owner decision.

## Compatibility (validated locally)

`scripts/deploy/validate_supabase_migrations.sh` runs the exact Supabase image
`17.6.1.084` locally and checks the following.

| Item | Result |
|---|---|
| `vector` available | 0.8.0, enabled into the `extensions` schema (as the dashboard does) |
| Role setup | `deploy/supabase-private-beta-role.sql` creates `ezo_app`: NOSUPERUSER, NOCREATEDB, NOCREATEROLE, NOBYPASSRLS, connection limit 20, `search_path public, extensions` |
| Migrations as `ezo_app` | 0001→0021 succeed; `alembic check` reports no drift |
| `deployment.check_database_role` logic | `ezo_app` is not privileged |
| Public Data API lockdown (migrations 0014/0015) | anon/authenticated have 0 privileges on EZO tables |
| Storage schema RLS (free-beta only) | **Not covered locally.** It needs the storage-api service. It is checked at startup by `deployment.check_database` and will refuse to start if it is wrong. |

The script never connects to a remote project. Run it with
`bash scripts/deploy/validate_supabase_migrations.sh [image]`.

## Design for a future, owner-approved Supabase project

- **Project:**
  - **dedicated to EZO**; never share a database, because migration 0015 revokes PUBLIC
    grants schema-wide;
  - region `eu-central-1`, close to the Hetzner and Render Frankfurt regions.
- **Connection:**
  - session pooler or direct connection on **port 5432**;
  - `sslmode=verify-full&sslrootcert=system`;
  - the transaction pooler (6543) is refused by the code.
- **Credentials:** only `ezo_app` (password set in the dashboard role UI) and, for free-beta,
  a server-only Storage secret key. **Never** the service-role key in the browser, and never
  the `postgres` password in the app.
- **Storage:**
  - a private bucket `ezo-private`, with no public URLs;
  - RLS stays enabled on `storage.objects` and `storage.buckets`, with **no** client-facing
    policies;
  - the app uses its server-only key; objects are immutable (`x-upsert:false`) and capped by
    `EZO_STORAGE_MAX_BYTES`.
- **Limits:**
  - **500 MB database (Free).** Stop ingestion at about 250 MB and monitor with
    `select pg_size_pretty(pg_database_size(current_database()))`;
  - 1 GB Storage and 5 GB egress.
- **Backups:**
  - Free has no point-in-time recovery; backup downloads are a dashboard feature on paid
    plans;
  - use `pg_dump` with the `ezo_app` role, or with the owner role from a trusted machine,
    into an age-encrypted R2 object, as in BACKUP_RESTORE_PLAN.md.

## Activation commands (only after approval; never `db push` or `db reset --linked`)

1. Dashboard → New project (EZO, `eu-central-1`). This is an owner action.
2. Dashboard → Database → Extensions → enable `vector` (schema `extensions`).
3. SQL Editor, as the owner: run `deploy/supabase-private-beta-role.sql`. Then set the
   `ezo_app` password in Database → Roles.
4. From a trusted machine: run `DATABASE_URL=<ezo_app session URL> uv run alembic upgrade head`
   in `apps/api`. The API entrypoint does the same on its first start.
5. Run `python -m ezo_api.deployment --after-migrations` with production env. It must exit 0.
