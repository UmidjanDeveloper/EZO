#!/bin/sh
set -eu

# Fail before migrations if production auth, TLS or storage is misconfigured.
python -m ezo_api.deployment
# One instance owns the disk and migrations; a failure prevents HTTP startup.
alembic upgrade head
exec uvicorn ezo_api.main:create_app --factory \
  --host 0.0.0.0 --port "${PORT:-8000}" --workers 1 \
  --no-access-log --no-server-header --timeout-graceful-shutdown 30
