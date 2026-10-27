# Camera and hand acceptance — 2026-10-27

Status: implementation candidate; **real hardware/model acceptance BLOCKED**.
This document supplements [the public contract](HUMANOID_PERCEPTION_CONTRACT.md).
No desktop/mobile/avatar implementation was edited; shipping wiring belongs to
Claude Max. Existing API methods are used through a structural adapter.

## What ran locally

- TypeScript checking, including the **actual** avatar example and browser fixture.
- 49 sensing unit tests: synthetic matrices/landmarks and deterministic lifecycle
  mocks. Includes real estimator result-shape conversion (nose/palm/velocity),
  invalid/extreme matrices, face/hand loss/reacquisition, stationary/moving hand,
  mirrored signed coordinates, stale/low-confidence frames, explicit-mode priority,
  reduced motion, revocation and late async inference/model initialization aborts.
- Chromium154.0.8037.57: five permission/capture/runtime tests plus one synthetic
  performance sample. **Fake camera/audio devices**, not physical acceptance.
  Actual getUserMedia/AudioWorklet are exercised; tracks and graph are stopped.
  Actual reviewed CPU WASM initializes inside the bundled worker, then deliberately
  invalid non-model bytes are rejected. No valid landmark model inference occurred.
- Existing avatar tests and full workspace unit/type/lint results are recorded in
  VALIDATION.md. No backend source/API contract changed in this workstream.

Environment: Linux cloud, Node24.19.0,5 logical CPUs, MemTotal34,906,016KiB
(~33.3GiB), managed Chromium154. This is **not** the owner's <16GB PC, Android,
Windows Electron or a4/8GB VM. A synthetic browser sample of10,000 attention updates
measured12.2ms and100 seconds of zero PCM measured41.4ms CPU elapsed at one checkpoint;
these are single-run bookkeeping costs, **not camera FPS/CPU/GPU/RAM/latency figures**.
Raw repeated measurements vary. No meaningful real-inference memory/GPU/battery or
clap-to-voice latency measurement is available; none is inferred from those numbers.

## Reproducible commands

From repo root after frozen pnpm10.28.0 install:

```sh
pnpm --filter @ezo/face-tracking typecheck
pnpm --filter @ezo/face-tracking test
pnpm --filter @ezo/avatar test
pnpm --filter @ezo/e2e exec playwright install chromium
pnpm --filter @ezo/face-tracking test:browser
pnpm --filter @ezo/face-tracking build:acceptance
```

In this managed environment only, set EZO_CHROMIUM_PATH=/usr/bin/chromium when
running test:browser. CI uses the pinned full Playwright Chromium new-headless channel (not the legacy
headless shell, which rejected fake media in the first hosted runs). EZO_BROWSER_REPORT
optionally writes JSON. The browser fixture is confined to tests/browser and is
not part of the real integration example or shipping clients. The example itself
has **no synthetic camera/hand/frame fallback**.

## Assets — must be completed before real inference

Official candidate URLs:

```
https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task
https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task
```

Both fetches returned policy403 here. Do not bypass restrictions or use arbitrary
mirrors. Review the official model cards, distribution terms and notices in an
approved environment. Record each reviewed model version, SHA256, license and
source in MODEL_LICENSE_REVIEW.txt. Model hashes are deliberately not invented.
Then from packages/face-tracking:

```sh
node scripts/prepare-assets.mjs /approved/face_landmarker.task FACE_SHA256 /approved/hand_landmarker.task HAND_SHA256 /approved/MODEL_LICENSE_REVIEW.txt
pnpm acceptance
```

Serve only127.0.0.1:8099 for acceptance (HTTPS for remote production). Preparation
makes no download and checks SDK's exact no-SIMD JS/WASM SHA256 plus both supplied
model hashes. It does not legally approve arbitrary files. Keep generated local
assets out of Git, preserve all required notices. Inspect CSP compatibility before
Claude enables this in a shipping client. No policy weakening is part of this PR.

## Remaining permissioned real-device test

The tester must authorize each camera/microphone access; no unattended access.

1. Open the existing-avatar acceptance page on a real Windows webcam device. Camera
   and mic indicators must be OFF. DevTools must show no capture or uploads.
2. Start Camera, grant browser/OS camera permission only. Microphone remains OFF.
   With reviewed real assets, verify actual model output and humanoid gaze move
   together. Left/right and up/down must match the mirrored preview. Test a portrait
   and landscape source without app-level crop/rotation.
3. Turn head, nod, tilt, translate face; eye fields must remain labelled approximate
   face target. Roll is telemetry only with the current renderer. Enter/exit hand,
   move left/right/up/down, hold stationary, cross two hands, occlude face/hand, dim
   lighting. Observe dwell/release and graceful neutral. No identity claims.
4. Deny permission, revoke it in OS/site settings, unplug/mute camera. No stale
   user-presence claim or automatic restart. Foregrounding requires a fresh action.
   Verify no lingering model worker, webcam indicator or live track after disable.
5. Repeatedly start/stop during prompt, video.play, model download/init and inference.
   Stop must release tracks immediately and terminate the worker; a late permission
   grant must immediately close. Hide/unmount avatar and background the app.
6. Run five minutes on owner PC with <16GB RAM, including voice speaking. Record
   browser/OS/CPU/RAM/camera resolution, normal vs lowPower requests, actual capture
   and inference rates, p50/p95 inferenceMs, frame age, main-thread long tasks,
   CPU/GPU, RSS growth and thermal/battery behavior. Render independently of inference.
   Targets15–30Hz are aspirational; SDK currently caps requests15Hz /8Hz low-power.
7. Claude must then test actual Electron permissions/CSP/context isolation and
   Android WebView continuous-video/AudioWorklet support. Capacitor photo support
   alone proves nothing. iOS remains future-only until an actual build/test exists.

Record signed/dated results without storing biometric landmarks/video by default.
Until those steps run, real-camera hand tracking and physical head following are
**BLOCKED**, even if simulated browser CI is green.
