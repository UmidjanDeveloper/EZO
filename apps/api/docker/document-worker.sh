#!/bin/sh
# Pins the executor image by its immutable ID, then serves queued documents.
set -eu
image="${EZO_EXECUTOR_IMAGE:-ezo-executor:local}"
id="$(docker image inspect --format '{{.Id}}' "$image")" || {
    echo "EZO document worker: executor image $image not found; run: docker compose up -d --build" >&2
    exit 1
}
echo "EZO document worker: executor image $image ($id)"
exec python -m ezo_api.student.worker \
    --worker-id "${EZO_DOCUMENT_WORKER_ID:-local-documents-1}" \
    --image "$id" \
    --ack-dedicated-executor-host
