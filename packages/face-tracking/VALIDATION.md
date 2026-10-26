# Validation — 2026-10-24

Base2d97025ccc1b6428da3a79b4b6eda9de370212ec, branch feat/isolated-face-tracking.
Local TypeScript `apps/web/node_modules/.bin/tsc -p packages/face-tracking/tsconfig.json`: PASS.
Local `apps/web/node_modules/.bin/vitest run packages/face-tracking/src/tracking.test.ts packages/avatar/src`:24 passed,0 failed,3 files.
Tests use synthetic matrices/mocked media streams, never physical-camera evidence.
The first run exposed signed-zero output; normalization was corrected, then tests
rerun. Initial package tooling could not write HOME and refused an unrelated module
purge; used writable XDG cache, lockfile-only generation and existing installed tools.
Lockfile change is only9-line importer; no dependency upgrades or app installs.

Hardware validation: **BLOCKED**, no /dev/video devices. Model asset/card/license
and SHA approval remain outstanding. SDK interface checked against published
0.10.32 declarations; actual WASM/model inference and CPU/GPU/browser performance
NOT run. Permissioned localhost test steps and exact remaining checks in README.
Hosted checks are not claimed run/passed here. No whole-backend/E2E rerun: existing
implementations unchanged. Renderer integration is a proposed port requiring
Claude review, not a working renderer setter or shipping avatar camera feature.
No merge/deploy/purchase/production config changes or video uploads.
