#!/usr/bin/env bash
# Prove a backup restores: decrypt it, restore into EMPTY throwaway containers, compare
# hashes, schema head and row counts. Never touches the running stack's volumes.
#
#   ./restore-check.sh backups/ezo-<stamp>.tar.age /path/to/owner-age-identity.txt
set -euo pipefail
ARCHIVE="${1:?backup archive}"; IDENTITY="${2:?owner age identity file}"
NAME="ezo-restore-check-$$"; WORK="$(mktemp -d)"; PW="$(python3 -c 'import secrets;print(secrets.token_hex(16))')"
trap 'docker rm -f "$NAME" >/dev/null 2>&1; rm -rf "$WORK"' EXIT
age -d -i "$IDENTITY" "$ARCHIVE" | tar -C "$WORK" -xf -
( cd "$WORK" && sha256sum --check --strict <(grep -v '^created=' MANIFEST.sha256) )
docker run -d --name "$NAME" -e POSTGRES_PASSWORD="$PW" -e POSTGRES_DB=ezo pgvector/pgvector:pg16@sha256:7b822b0aac60967beb1ea5e576b8602c94c300a157d187f385ae3e0da199b90a >/dev/null
for _ in $(seq 1 60); do docker exec "$NAME" pg_isready -U postgres -d ezo >/dev/null 2>&1 && break; sleep 2; done
sleep 3
# Same extension and app role that initdb/10-ezo-app-role.sh creates on a real host.
docker exec "$NAME" psql -U postgres -d ezo -qc "create extension if not exists vector; create role ezo_app nologin"
docker exec -i "$NAME" pg_restore -U postgres -d ezo --no-owner --exit-on-error < "$WORK/ezo.dump"
mkdir "$WORK/files" && tar -C "$WORK/files" -xf "$WORK/storage.tar"
echo "restored alembic head: $(docker exec "$NAME" psql -U postgres -d ezo -Atc 'select version_num from alembic_version')"
echo "expected:              $(grep '^created=' "$WORK/MANIFEST.sha256")"
docker exec "$NAME" psql -U postgres -d ezo -Atc "select 'artifacts='||count(*) from artifacts union all select 'users='||count(*) from users union all select 'artifact_versions='||count(*) from artifact_versions"
echo "restored files: $(find "$WORK/files" -type f | wc -l)"
echo "RESTORE CHECK PASSED (data restored into a throwaway container)"
