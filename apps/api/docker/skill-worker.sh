#!/bin/sh
# Pins the EZO API image by its immutable ID, then runs owner-approved skills, each in its
# own throw-away container (no network, read-only, 256 MiB, 32 PIDs, 20 s, UID 10001).
set -eu
image="${EZO_SKILL_IMAGE:-ezo-api:local}"
id="$(docker image inspect --format '{{.Id}}' "$image")" || {
    echo "EZO skill worker: image $image not found; run: docker compose up -d --build" >&2
    exit 1
}
echo "EZO skill worker: image $image ($id)"
exec python -m ezo_api.skills.worker \
    --worker-id "${EZO_SKILL_WORKER_ID:-local-skills-1}" \
    --image "$id"
