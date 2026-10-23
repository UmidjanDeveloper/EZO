#!/usr/bin/env bash
# Generate host-local secrets for deploy/primary. Run ON THE PRIMARY HOST, once.
# Writes only into ./secrets (git-ignored, mode 700) and prints NO secret values.
# Re-running refuses to overwrite: rotation is a deliberate procedure
# (docs/deployment/SECRETS_AND_PERMISSIONS.md).
set -euo pipefail
cd "$(dirname "$0")"
umask 077
if [ -e secrets/.generated ]; then
  echo "secrets/ already exists; refusing to overwrite (see the rotation runbook)." >&2
  exit 1
fi
mkdir -p secrets/db-tls
rand() { python3 -c 'import secrets; print(secrets.token_hex(32))'; }
{
  echo "EZO_DB_ADMIN_PASSWORD=$(rand)"
  echo "EZO_DB_APP_PASSWORD=$(rand)"
  echo "EZO_API_TOKEN=$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
} > secrets/compose.env

# Private CA for the database connection (verify-full needs hostname "db" in the cert).
openssl req -x509 -newkey rsa:3072 -nodes -days 1825 -subj "/CN=EZO DB CA" \
  -keyout secrets/db-tls/ca.key -out secrets/db-tls/ca.crt 2>/dev/null
openssl req -newkey rsa:3072 -nodes -subj "/CN=db" \
  -keyout secrets/db-tls/server.key -out secrets/db-tls/server.csr 2>/dev/null
printf 'subjectAltName=DNS:db\nextendedKeyUsage=serverAuth\n' > secrets/db-tls/ext.cnf
openssl x509 -req -in secrets/db-tls/server.csr -CA secrets/db-tls/ca.crt \
  -CAkey secrets/db-tls/ca.key -CAcreateserial -days 825 \
  -extfile secrets/db-tls/ext.cnf -out secrets/db-tls/server.crt 2>/dev/null
rm -f secrets/db-tls/server.csr secrets/db-tls/ext.cnf
# PostgreSQL (uid 999 in the official image) must own a 0600 key; the CA cert is public.
chmod 600 secrets/db-tls/server.key secrets/db-tls/ca.key
chmod 644 secrets/db-tls/ca.crt secrets/db-tls/server.crt
if [ "$(id -u)" = 0 ]; then chown 999:999 secrets/db-tls/server.key; else
  echo "NOTE: run 'sudo chown 999:999 secrets/db-tls/server.key' before the first start."; fi
# The API/worker containers run as uid 10001 and must read the CA certificate.
chmod 755 secrets secrets/db-tls
# Keep ca.key offline after issuing the server certificate.
touch secrets/.generated
echo "Generated secrets/compose.env and secrets/db-tls/. Start with:"
echo "  docker compose --env-file secrets/compose.env --env-file primary.env up -d --build"
