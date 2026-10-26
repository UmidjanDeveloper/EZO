# EZO camera tracking — isolated integration candidate

Base: integration2d97025 (PR35 humanoid). Open PR36/37 observed before changes.
Only this package and its additive lockfile importer are owned here. Existing
avatar, web, desktop, mobile, voice and backend implementations are untouched.
No integration approval is implied. Hardware acceptance is **BLOCKED**: this cloud
machine has no `/dev/video*`. All automated fixtures are synthetic/mocked.

## Public API and ownership

`CameraTracker({video,indicator,createEstimator,onFrame,onStatus})`: camera OFF on
construction. Call `start()` only in an explicit user click, over localhost/HTTPS.
The indicator must be visibly rendered next to Enable/Disable controls (not CSS
hidden by the consumer). Status: off/requesting/tracking/lost/error; stream-active
requesting also says Camera active. `stop()` immediately stops all acquired tracks,
detaches video, cancels timers, closes inference and clears output. A permission
promise cannot be dismissed programmatically; a late grant is immediately stopped.
`setVisible(false)` and document backgrounding stop capture; return to foreground
requires another click. Consumer must call stop on unmount/pagehide and handle
callbacks without throwing. Hidden component consumers must call setVisible.

TrackingFrame yaw/pitch/roll/gazeX/gazeY are normalized[-1,1], timestamp monotonic
browser milliseconds. Head angles are approximate canonical-face matrix Euler
rotations, saturated at yaw60°, pitch/roll45°. MediaPipe gaze fields are approximate nose/face-position targets in unmirrored
camera coordinates (head aim fallback when a nose landmark is missing),
**not calibrated eye tracking**, physical position, distance or face identity.
Confidence1 means a single model-accepted face/matrix, not a probability of angular
accuracy. No face→null immediately (no stale pose). Model thresholds0.6 apply in
the demo, engine acceptance0.5 applies to pluggable estimators. One-face mode may
select one of several people; no identity lock or continuity guarantee.

`Smoother` uses100ms exponential response and rejects stale timestamps. Inference
runs serially at adaptive4–15Hz, capture640x480/15fps max. Duplicate/unready video
frames yield lost, never invented motion. Initial CPU delegate works without GPU;
unsupported camera/WASM or model load failure releases tracks and reports error.
Synchronous MediaPipe inference can block the UI for one call; disabling cannot
interrupt that call. Worker-based inference is a later coordinated improvement;
there is no measured low-end latency guarantee or claimed RAM benchmark.

## Actual MediaPipe integration and licensing

Selected optional runtime: `@mediapipe/tasks-vision` **0.10.32**, Apache-2.0 per
npm metadata and google-ai-edge/mediapipe LICENSE. Inspected published vision.d.ts,
README, bundle layout: FaceLandmarker VIDEO detectForVideo, transformation matrix,
FilesetResolver SIMD/no-SIMD WASM. Published unpacked payload23,601,614 bytes.
No package source copied, no runtime dependency added to existing apps. Exact
SDK distribution integrity from npm:
`sha512-3tiAZnmKloYnRXYoO3dKltTUGnqeCwzC4lV03uY0vCsE+aveJTyEVQyZHOlQGQNsjK+gRHzkf9q08C99Qm2K0Q==`.
Upstream: https://github.com/google-ai-edge/mediapipe ;
https://www.npmjs.com/package/@mediapipe/tasks-vision/v/0.10.32 .
Model weights have separate distribution terms: **not vendored or approved by this
PR**. Before use Claude must review the exact official Face Landmarker model card,
license and redistribution terms, pin model SHA256, retain SDK/model notices and
review browser support/security advisories. SDK license alone does not license an
arbitrary downloaded model. No unverified download script/CDN fallback is provided.
Native FaceDetector is not selected: support varies and detection alone lacks pose.

## Permissioned hardware test / real integration example

1. Obtain the reviewed SDK above, retain Apache license/notices. Copy its
   vision_bundle.mjs and wasm directory into demo/assets. Supply a separately
   approved face_landmarker.task and record SHA256/license in the test report.
2. Compile from repository root:
   `apps/web/node_modules/.bin/tsc packages/face-tracking/src/index.ts --target ES2022 --module ESNext --lib ES2022,DOM --outDir packages/face-tracking/demo/build`.
3. Serve only localhost: `python -m http.server 8099 --bind 127.0.0.1 --directory packages/face-tracking/demo`.
4. Open localhost8099. Confirm off before click, click Enable, grant real camera.
   Turn left/right, nod, tilt, cover face; observe live normalized JSON then lost.
   This is real camera inference when run with those assets, not a synthetic demo.
5. Disable, deny permission, disconnect webcam, hide tab, reopen, rapidly enable/
   disable during prompt/model load. Browser camera indicator must extinguish;
   no automatic foreground restart; lost/error must not retain an old frame.
6. DevTools Network must show only local asset loading, no frame POST/WebSocket;
   inspect no recordings/storage. Measure five-minute CPU/RSS/inference p50/p95 and
   frame cadence on a <16GB machine in CPU mode and with avatar speaking. Test
   Chrome/Edge/Firefox/Safari separately. None of these hardware checks ran here.

## Claude Max integration steps (approval required for renderer edits)

Existing `@ezo/avatar` exports EzoAvatar/setState/setLevel/destroy; it has **no**
external head-motion setter. `driveAvatar(MotionPort,frame)` is a typed example port,
not a claim that current EzoAvatar accepts it. After coordination Claude can add a
reviewed setHeadAim port, apply bounded radians to point and silhouette transforms
consistently, implement roll only if renderer supports it, and return to idle on
null/lost. Preserve state/voice energy scheduling: tracking never calls setState or
setLevel. Honor reduced-motion preferences. Add visual tests before wiring into
web/desktop/mobile. Wire visible indicator, explicit click, unmount/pagehide stop,
intersection visibility and no auto-restart. Electron permission and Capacitor
camera video-stream support require separate platform review; photo capture is not
continuous tracking. No platform permissions/production configuration changed here.

## Provider-independent voice profile proposal (no implementation)

Proposed data contract: `{language:'uz'|'en'|'ru', timbre:'deep-natural',
 delivery:'calm', style:'neutral'|'warm'|'focused', rate:0.85..1.1,
 providerVoiceId?:string}`. IDs are server/config-selected and provider validated,
not model-generated. Select a naturally low register with native-language samples,
not destructive pitch shifting. Preserve STT/TTS adapters owned by Claude. A voice
playback clock + actual amplitude/viseme events may drive existing setLevel; head
tracking is an independent additive channel. On interrupted playback clear speech
energy without restarting camera. Listening/thinking/error state remains owned by
existing orchestration. Real Uzbek/English/Russian pronunciation and perceived
voice quality require owner listening acceptance, not an invented score.
