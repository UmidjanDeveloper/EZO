#!/usr/bin/env bash
# Validate EZO's Alembic migrations and production database preflights against a LOCAL,
# disposable copy of the Supabase Postgres image. Never point this at a remote project.
#
# What it reproduces (as the Supabase dashboard would for a new dedicated project):
#   1. `vector` enabled in the `extensions` schema by the project owner role;
#   2. deploy/supabase-private-beta-role.sql run by that role, creating `ezo_app`;
#   3. `alembic upgrade head` + `alembic check` run AS `ezo_app` (what entrypoint.sh does);
#   4. ezo_api.deployment's role / pgvector / anon+authenticated exposure checks.
# Storage-schema RLS checks need the separate storage-api service and are NOT covered.
#
# Usage: scripts/deploy/validate_supabase_migrations.sh [image]
set -euo pipefail

IMAGE="${1:-mirror.gcr.io/supabase/postgres:17.6.1.084}"
NAME="ezo-supabase-migration-check-$$"
PORT="${EZO_CHECK_PORT:-55433}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ADMIN_PW="$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')"
APP_PW="$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')"

cleanup() { docker rm -f "$NAME" >/dev/null 2>&1 || true; }
trap cleanup EXIT

docker run -d --name "$NAME" -e POSTGRES_PASSWORD="$ADMIN_PW" \
  -p "127.0.0.1:${PORT}:5432" "$IMAGE" >/dev/null
for _ in $(seq 1 90); do
  if PGPASSWORD="$ADMIN_PW" psql -h 127.0.0.1 -p "$PORT" -U postgres -d postgres -Atqc 'select 1' \
    >/dev/null 2>&1; then break; fi
  sleep 2
done

admin() { PGPASSWORD="$ADMIN_PW" psql -v ON_ERROR_STOP=1 -h 127.0.0.1 -p "$PORT" -U postgres -d postgres -Atq "$@"; }

echo "== server: $(admin -c 'select version()')"
admin -c "create extension if not exists vector with schema extensions"
admin -f "$ROOT/deploy/supabase-private-beta-role.sql"
admin -c "alter role ezo_app password '$APP_PW'"

APP_URL="postgresql://ezo_app:${APP_PW}@127.0.0.1:${PORT}/postgres"
cd "$ROOT/apps/api"
echo "== alembic upgrade head (as ezo_app)"
DATABASE_URL="$APP_URL" uv run --frozen alembic upgrade head >/dev/null
echo "== alembic check (models and migrations in sync)"
DATABASE_URL="$APP_URL" uv run --frozen alembic check

echo "== production database preflights"
DATABASE_URL="$APP_URL" uv run --frozen python - <<'PY'
import os
from sqlalchemy import create_engine, text
from ezo_api.db.session import to_sync_url
from ezo_api.deployment import PRIVILEGED_ROLE_SQL

engine = create_engine(to_sync_url(os.environ["DATABASE_URL"]))
with engine.connect() as c:
    privileged = c.scalar(text(PRIVILEGED_ROLE_SQL))
    vector_table = c.scalar(text("select to_regclass('public.pgvector_entries')"))
    exposed = c.scalar(text(
        "SELECT count(*) FROM pg_roles r CROSS JOIN pg_class c "
        "JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE r.rolname IN ('anon','authenticated') AND n.nspname='public' "
        "AND c.relkind IN ('r','p','v','m','f') "
        "AND (has_table_privilege(r.oid, c.oid, 'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER') "
        "OR has_any_column_privilege(r.oid, c.oid, 'SELECT,INSERT,UPDATE,REFERENCES'))"))
    tables = c.scalar(text("select count(*) from pg_tables where schemaname='public'"))
    head = c.scalar(text("select version_num from alembic_version"))
print(f"tables={tables} alembic_head={head} app_role_privileged={privileged} "
      f"pgvector_entries={vector_table} anon_authenticated_exposed={exposed}")
assert privileged is False, "ezo_app must not be privileged"
assert vector_table is not None, "pgvector_entries missing"
assert exposed == 0, "anon/authenticated can reach EZO tables"
print("OK: migrations and database preflights pass on this image")
PY
