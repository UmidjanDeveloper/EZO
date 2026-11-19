#!/usr/bin/env bash
# One command to start (or update) EZO on the primary host, after the owner has prepared the
# host (docs/master/SERVER_DEPLOY_UZ.md). It buys nothing and changes no DNS.
#   ./deploy.sh            # first start or update to the checked-out commit
set -euo pipefail
cd "$(dirname "$0")"
command -v docker >/dev/null || { echo "Docker is not installed." >&2; exit 1; }
docker compose version >/dev/null || { echo "Docker Compose v2 is required." >&2; exit 1; }
if [ ! -f primary.env ]; then
  echo "primary.env is missing: cp primary.env.example primary.env and set the domains first." >&2
  exit 1
fi
if grep -Eq '^EZO_(WEB|API)_DOMAIN=.*example\.com' primary.env; then
  echo "Set EZO_WEB_DOMAIN and EZO_API_DOMAIN in primary.env (still example.com)." >&2
  exit 1
fi
if [ ! -f secrets/compose.env ]; then
  ./bootstrap-secrets.sh
fi
git -C ../.. log -1 --format='Deploying commit %h (%cs): %s'
docker compose --env-file secrets/compose.env --env-file primary.env config --quiet
docker compose --env-file secrets/compose.env --env-file primary.env up -d --build --wait db api web caddy
docker compose --env-file secrets/compose.env --env-file primary.env up -d student-worker
. ./primary.env
echo "EZO is up:"
echo "  web: https://${EZO_WEB_DOMAIN}"
echo "  api: https://${EZO_API_DOMAIN}/api/health"
echo "Owner sign-in: Settings → API token = EZO_API_TOKEN from secrets/compose.env"
