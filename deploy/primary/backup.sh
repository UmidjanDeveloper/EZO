#!/usr/bin/env bash
# Matched backup of the EZO primary host: PostgreSQL (logical dump) + /app/storage files,
# taken back-to-back and encrypted to the OWNER'S age public key. The host can create
# backups but cannot read them; the private key stays offline with the owner.
#
#   EZO_BACKUP_AGE_RECIPIENT=age1...  ./backup.sh [output-dir]
#   Optional off-site copy: EZO_BACKUP_RCLONE_REMOTE=r2:ezo-backups (rclone, R2 S3 API).
#
# A backup is only trusted after ./restore-check.sh has restored it into empty containers.
set -euo pipefail
cd "$(dirname "$0")"
: "${EZO_BACKUP_AGE_RECIPIENT:?set EZO_BACKUP_AGE_RECIPIENT to the owner age public key}"
OUT="${1:-./backups}"
PROJECT="${COMPOSE_PROJECT_NAME:-ezo-primary}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
umask 077
mkdir -p "$OUT"

# 1. Database: consistent snapshot of the ezo database (custom format, compressed).
docker exec "${PROJECT}-db-1" pg_dump -U postgres -d ezo --format=custom --compress=6 \
  --no-owner > "$WORK/ezo.dump"
# 2. Files: the durable artifact/storage volume, read-only mount.
docker run --rm -v "${PROJECT}_ezo-storage:/data:ro" --entrypoint tar pgvector/pgvector:pg16@sha256:7b822b0aac60967beb1ea5e576b8602c94c300a157d187f385ae3e0da199b90a \
  -C /data -cf - . > "$WORK/storage.tar"
# 3. Manifest with hashes so a restore can prove it got exactly these bytes.
HEAD_REV="$(docker exec "${PROJECT}-db-1" psql -U postgres -d ezo -Atc "select version_num from alembic_version")"
(cd "$WORK" && sha256sum ezo.dump storage.tar > MANIFEST.sha256)
echo "created=$STAMP alembic_head=$HEAD_REV" >> "$WORK/MANIFEST.sha256"
tar -C "$WORK" -cf - ezo.dump storage.tar MANIFEST.sha256 \
  | age -r "$EZO_BACKUP_AGE_RECIPIENT" > "$OUT/ezo-$STAMP.tar.age"
echo "Encrypted backup: $OUT/ezo-$STAMP.tar.age ($(du -h "$OUT/ezo-$STAMP.tar.age" | cut -f1))"

if [ -n "${EZO_BACKUP_RCLONE_REMOTE:-}" ]; then
  rclone copy --immutable "$OUT/ezo-$STAMP.tar.age" "$EZO_BACKUP_RCLONE_REMOTE/"
  echo "Copied off-site to $EZO_BACKUP_RCLONE_REMOTE"
fi
