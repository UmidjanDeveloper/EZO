# Humanoid perception contract — 2026-10-27

Integration base: `abb9016859acc002f31029212dc2e4a13946b435` (PR55). Branch:
`feat/humanoid-perception`. This is an additive SDK for the existing EZO product,
not a shipping desktop/mobile integration. Claude Max owns avatar, web, Windows,
Android and voice UI/provider wiring. No such production implementation is changed.
The repository's prior backend candidate is already included in this base.

## Data flow and trust

Explicit camera action → **existing** CameraTracker → one transferred ImageBitmap
→ dedicated CPU MediaPipe worker → face/hand landmarks → normalized target/motion
→ AttentionController → existing EzoAvatar.setGaze. Independent render cadence.
Explicit microphone action → local AudioWorklet → bounded 10ms mono PCM windows
→ ClapDetector → acknowledgement-only intent → client's authenticated existing TTS
and actual playback bridge. Neither sensor enables STT or authorizes agent actions.

No raw video/audio upload, recordings, persistent landmarks, recognition database,
person identification or cloud inference is implemented. Model/SDK assets are
fetched locally from the same origin, credentials omitted, redirects rejected,
size bounded and SHA256 checked before use. SDK loader and WASM hashes are fixed in
`src/vision.ts`, so an arbitrary caller-supplied script hash cannot authorize a
replacement loader. Face/hand model hashes are integrator-approved configuration,
not model-generated input. A web worker is a UI scheduling/cancellation boundary,
**not an OS security sandbox**. Model parsing still requires trusted reviewed assets.

## Public imports

```ts
import {
  HumanoidPerception, applyMotion, VoiceReaction, acknowledgement,
  type VisionAssets, type Language, type AcknowledgementPlayer,
  type PerceptionFrame, type MotionIntent, type ClapDetected,
} from '@ezo/face-tracking';
```

`TrackingFrame` remains backward compatible. Angles/targets are normalized[-1,1],
not measured gaze or degrees. `PerceptionFrame` carries face|null, up to two hands,
monotonic timestampMs, actual worker inferenceMs and optional inter-palm distance.
Hands contain normalized x/y, normalized-units/second velocity, moving hysteresis
and temporary handedness label. Labels can swap under occlusion; they are not IDs.
`confidence` is a conservative accepted-quality heuristic (face0.8 after configured
SDK thresholds, hands at most0.8 using handedness acceptance), **not a calibrated
pose, detection or angular-accuracy probability**. SDK doesn't expose those scores.

`MotionIntent` has source(face/hand/eye/neutral), yaw/pitch/roll, confidence,
timestampMs, and state(neutral/face_attention/hand_attention/following_head/
listening/speaking/attention_lost). `eye` is reserved: no eye/iris estimator exists.
`applyMotion` uses current `setGaze({yaw,pitch}|null)` only; it never changes activity
or speech level. Current renderer derives eyes/head together and does not consume
independent roll. Actual radians are renderer-limited to yaw0.25/pitch0.15 via its
existing API. No facial identity, physical gaze accuracy or roll animation claim.

Priority: explicit listening/speaking → moving hand after60ms dwell → visible face
position (75%) plus approximate head rotation (25%) → neutral. Hand attention releases after700ms inactivity;
frames expire after500ms. Stale/future/nonfinite frames are rejected. Exponential
140ms target smoothing is independent of rendering frequency. Movement enter/exit
thresholds0.08/0.04 normalized units/s reduce chatter. Reduced motion zeros target
movement; camera inference can separately be disabled. There is no person continuity
lock across multiple people. Stationary hands never steal attention from a face.

Camera decoded coordinates x(right),y(down) become target x(right),y(up). Set
`mirrored:true` exactly once when preview is CSS-mirrored; do not mirror inputs again.
Normalized axes account for aspect ratio without pixel stretching calculations.
Use the full uncropped decoded frame. Browser-native decoded rotation is respected;
additional app CSS rotation/cropping requires a coordinated transform and testing.
Low-light/partial occlusion produce no accepted face/hand, not invented motion.
No calibrated eye target, physical depth or universal rotation calibration is supplied.

## Exact Claude integration example

```ts
const player: AcknowledgementPlayer | null = authenticatedExistingVoiceBridge;
const reaction = new VoiceReaction(player, event => {
  if (event.type === 'start') perception.setInteraction('speaking');
  if (event.type === 'level') avatar.setLevel(event.level); // REAL decoded audio RMS
  if (event.type === 'end' || event.type === 'error' || event.type === 'unavailable') {
    avatar.setLevel(0);
    perception.setInteraction(null);
  }
});
const perception = new HumanoidPerception({
  video, cameraIndicator, microphoneIndicator, assets: reviewedAssets as VisionAssets,
  mirrored: true, reducedMotion: matchMedia('(prefers-reduced-motion: reduce)').matches,
  lowPower: true, clap: { sensitivity: 1, requireHands: false },
  onMotionIntent: intent => applyMotion(avatar, intent),
  onHandMovement: hands => showEphemeralHandStatus(hands),
  onClapDetected: event => void reaction.react(acknowledgement(event, selectedLanguage as Language)),
  onStatus: showSensorStatus, onError: showSensorError,
  onPermissionRevoked: sensor => showPermissionRequired(sensor),
});
startCameraButton.onclick = () => void perception.startTracking();
stopCameraButton.onclick = () => perception.stopTracking();
startClapButton.onclick = () => void perception.startClapDetection();
stopClapButton.onclick = () => perception.stopClapDetection();
stopAllButton.onclick = () => { perception.stop(); reaction.stop(); };
// React unmount, hidden avatar, app background and pagehide MUST also stop playback.
// SetVisible(false) stops BOTH capture streams. Showing never restarts them.
```

Callbacks are synchronous and must not throw. Provide visible indicators/stop
controls in the shipping UI. Bind sensor start to **separate explicit gestures**.
No constructor requests permission. No eager requestPermissions() method requests
both sensors. startTracking/startClapDetection invoke their separate browser flows.
`trackingStatus` and `currentAttentionTarget` expose current state; listeners are
constructor callbacks, not a competing client state machine.

`setInteraction('speaking')` suppresses clap processing while actual provider audio
plays, reducing self-triggering. Listening mode requires separate existing consent;
a clap response has startListening:false. Active speaker localization is not supplied.
The selected conversation language must come from app settings/conversation context,
never face/head data. Callback samples contain no identity or durable tracking key.

## Lifecycle and bounded work

CameraTracker now accepts sync **or async** estimators. Its factory receives an
AbortSignal; old zero-argument factories remain valid. Optional Estimator.hasTarget reports
hand-only target availability without fabricating a legacy TrackingFrame; status
tracking includes accepted hands while onFrame stays face|null. Expired async face
frames (>500ms) are rejected. A frozen video timestamp transitions to lost after
500ms; a single ordinary duplicate does not falsely reset tracking. Stop aborts pending worker
initialization/inference, terminates it, releases media tracks, detaches video,
removes track/visibility/pagehide/permission listeners and cancels timers. Visibility/pagehide guards are installed before permission is requested, not
only after grant. Late permission grants after hide/disable are stopped; returning to foreground requires another action.
Track ended/mute stops capture; Permissions API denied transitions additionally
report confirmed revocation where supported. Other interruptions are onError and
must not be mislabeled confirmed permission revocation. Unsupported permission
querying falls back to ended/mute. No browser/OS permission settings are changed.

Low-power capture requests320×240/8fps; normal640×480/15fps max. These are browser
constraints, not achieved inference benchmarks. The serial adaptive interval is
4–15Hz (4–8Hz low-power); at most one bitmap is in flight. Decode/inference costs
can lower cadence further.15–30 measured inference FPS is **not achieved evidence**.
Worker requests have15s deadline, model files12MB each, WASM20MB, loader2MB bounds.
On deadline/error worker terminates, capture closes, no main-thread executor fallback.
CPU delegate/no-SIMD supports devices without a usable GPU; no camera/WASM means
honest error and ordinary idle/manual interaction. Platforms without ImageBitmap,
Worker or AudioWorklet are unsupported and fail closed. No continuous cloud audio. PCM uses one-window acknowledgement backpressure;
busy UI drops input instead of accumulating windows.

## Asset selection and release gate

SDK: `@mediapipe/tasks-vision` **0.10.32**, npm SRI
`sha512-3tiAZnmKloYnRXYoO3dKltTUGnqeCwzC4lV03uY0vCsE+aveJTyEVQyZHOlQGQNsjK+gRHzkf9q08C99Qm2K0Q==`.
Inspected published vision.d.ts, README, JS bundle and WASM distribution. Apache-2.0
SDK metadata and upstream LICENSE at commit
`7c0ddec593580937fad5fcbcb792ad4fcbc3b67d` reviewed. Attribution/license in
`packages/face-tracking/THIRD_PARTY_NOTICES.md` and `licenses/MediaPipe-Apache-2.0.txt`.
See runtime source for exact SHA256 of both no-SIMD assets; preparation script
checks the same values. npm audit found no SDK advisory; that is not a WASM audit.

Candidate official models (not downloaded, selected, redistributed or approved):
- face_landmarker/face_landmarker/float16/**1**/face_landmarker.task
- hand_landmarker/hand_landmarker/float16/**1**/hand_landmarker.task

Both official storage.googleapis.com downloads were403-blocked by this environment's
network policy. No bypass/mirror was used. **Model license/card/security review,
actual model SHA256 and live inference validation remain BLOCKED.** SDK Apache
license does not establish separate weight terms. No invented weight hashes.
`prepare-assets.mjs` requires approved local model files, pre-reviewed expected
hashes and a substantive model-license-review file, and makes no network request.
The script cannot itself provide legal approval. It refuses a changed SDK runtime.
Do not check models, private recordings or generated artifacts into Git.

Vite/esbuild classic worker bundling is required because the SDK WASM loader uses
importScripts. The acceptance command builds then previews the actual bundle;
raw TypeScript or a dev-server module worker is not the supported integration.
Coordinate shipping bundler/CSP with Claude: same-origin worker/script assets,
worker blob loader/AudioWorklet blob modules and local WASM compilation must be
permitted by a narrowly reviewed policy. No global unsafe-eval/CSP relaxation or
Electron contextIsolation/nodeIntegration changes are authorized by this contract.
If the current app policy disallows this path, keep sensing disabled pending review.

## Release status

Implementation candidate, **PARTIAL/BLOCKED**, not production ready. Actual SDK CPU
WASM initializes in a browser worker and rejects a deliberate invalid model fixture;
that is **not** successful face/hand inference. Permissioned fake-media tests are
explicit simulations. No physical camera, microphone or speaker in this cloud host;
no live paid provider call, real trilingual playback, low-RAM/Android measurement,
or shipping client wiring is claimed. Remaining exact checks are in the two acceptance
documents. Do not merge/deploy/activate a camera without owner action and review.
