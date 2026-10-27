# Perception validation — 2026-10-27

Base `abb9016859acc002f31029212dc2e4a13946b435`; feature branch
`feat/humanoid-perception`. Existing merged backend/UI work is preserved.
No production avatar, web, desktop, mobile or voice-provider files changed.
One additive MediaPipe runtime dependency0.10.32 (no transitive npm dependency);
Vite8.3.4 is an already locked dev tool exposed for the existing package's harness.

## Local evidence

| Check | Result | Scope/limitation |
|---|---|---|
| Frozen pnpm10.28.0 install | PASS | install scripts disabled locally; no lockfile drift |
| Workspace lint | PASS | includes web ESLint and package/client tsc |
| Workspace TypeScript | PASS | including e2e, actual-avatar example and browser SDK fixture |
| Sensing unit tests |53 passed,0 failed | synthetic landmarks/PCM and mocked lifecycle |
| Avatar unit |15 passed,0 failed | current existing renderer contracts |
| Shared unit |10 passed,0 failed | existing contracts |
| Web unit |97 passed,0 failed | existing UI/API inventory |
| Android unit |19 passed,0 failed | not a physical Android run |
| Windows unit |69 passed,2 skipped,0 failed | Windows-only live tests skipped on Linux |
| Chromium browser |6 passed,0 failed | five simulated sensor/runtime checks plus synthetic performance sample |
| Existing-avatar acceptance bundle | PASS | Vite bundled classic worker, not live model acceptance |
| npm full audit |0 HIGH,0 CRITICAL,1 MODERATE | existing uuid7.0.3 via Capacitor CLI/xcode; GHSA-w5hq-g745-h8pq |
| Physical webcam/mic/speakers | BLOCKED | no /dev/video* or /dev/snd |
| Actual face/hand model inference | BLOCKED | official model fetches policy403; no reviewed weights/hashes |
| Trilingual provider audio heard | BLOCKED | no configured provider/live paid call/physical playback |
| Real <16GB hardware performance | BLOCKED | cloud host ~33.3GiB/5CPU, not owner PC |

Workspace total: **263 passed,2 skipped,0 failed** (includes53 sensing tests).
The exact tests exercise face/head position, hand landmark conversion/motion,
attention ordering/smoothing/mirroring/reduced motion, low-confidence/stale input,
malformed matrices, permission denial/revocation/interruption, async cancellation,
late grants, repeated cleanup, local PCM evidence and safe voice-unavailable behavior.

Browser automation uses Chromium154.0.8037.57 with explicitly fake capture devices.
Actual pinned CPU WASM loads in a worker and rejects invalid fixture model bytes.
This does not prove valid-model inference, real clap recognition or physical motion.
No synthetic event/frame fallback exists in the real-avatar example. No raw images,
landmarks or audio recordings are in test evidence. Synthetic-only performance
sample and environment limits are documented in CAMERA_GESTURE_ACCEPTANCE.md.

The full backend/database/native Docker suites and shipping E2E are delegated to
unchanged hosted CI jobs for this branch; they were not rerun locally for this
isolated TypeScript change. Hosted status and exact head are recorded separately
once available. Initial hosted browser runs exposed Not supported when opening fake
camera/microphone in the default headless shell. The harness now explicitly selects
the full Chromium new-headless channel and a real button click for AudioContext
activation; no capture/cleanup assertions were removed. Each browser case has a30s
deadline and context cleanup, and the CI step has a5min limit. A later hosted lint run exposed a missing direct Node test-type dependency for
the trusted-worklet node:vm regression. @types/node22.20.5 (already locked in the
repository) is now explicit, with node types configured; no assertion or type
checking was disabled. A green hosted run cannot close the model/hardware gates above.
The earlier2026-10-24 mocked-only package evidence remains in Git history.

## Remaining review gates

1. Approved official weight license/card/security review + actual SHA256 values.
2. Successful real landmark inference and <16GB PC benchmark.
3. Claude shipping bundler/CSP/permission and avatar/voice integration review.
4. Real clap/noise/speech corpus and trilingual natural provider playback acceptance.
5. Existing platform/backend security risks remain subject to their master report;
   this PR does not claim to close native libxml2/K4/general product release gates.

No merge, deployment, paid activation, real provider API call, production credential
creation or settings/protection change occurred.
