#!/bin/sh
# Runs once, on an empty data directory, as the postgres superuser (official image hook).
# Creates the non-privileged role the API and workers use; EZO's startup refuses
# superuser/CREATEDB/CREATEROLE/BYPASSRLS/REPLICATION roles.
set -eu
psql -v ON_ERROR_STOP=1 --username postgres --dbname ezo \
  -v app_password="$EZO_DB_APP_PASSWORD" <<'SQL'
CREATE EXTENSION IF NOT EXISTS vector;
CREATE ROLE ezo_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS
  CONNECTION LIMIT 30 PASSWORD :'app_password';
GRANT CONNECT ON DATABASE ezo TO ezo_app;
-- The API applies migrations at startup, so the app role owns its own schema objects.
GRANT USAGE, CREATE ON SCHEMA public TO ezo_app;
REVOKE ALL ON DATABASE ezo FROM PUBLIC;
GRANT CONNECT ON DATABASE ezo TO ezo_app;
SQL
# Only TLS connections from the private network may use passwords (no plaintext TCP).
cat > "$PGDATA/pg_hba.conf" <<'HBA'
local   all  postgres              peer map=admin
local   all  all                   scram-sha-256
hostssl ezo  ezo_app  0.0.0.0/0    scram-sha-256
hostssl ezo  ezo_app  ::/0         scram-sha-256
HBA
# Container-local administration (healthcheck, backups via docker exec) maps root -> postgres.
cat > "$PGDATA/pg_ident.conf" <<'IDENT'
admin  postgres  postgres
admin  root      postgres
IDENT
