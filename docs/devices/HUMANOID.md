# EZO energy presence

EZO's presence is a luminous, energy-based head and upper torso on a black canvas:
electric-cyan scanning contours, fine neck/shoulder filaments, an amber facial light
core, drifting particles and cyan/gold waves. It is **not** a skin avatar, VRM, stock
model, conventional robot or generic sphere. The same framework-free renderer runs in
the web voice stage, the Windows pill and the Android voice stage.

> **Reference limitation.** The requested `humanoid-demo.mp4` was not available in the
> workspace. This implementation follows the written visual direction; frame-by-frame
> fidelity to that video has not been verified. The UI states this limitation in the
> device settings.

## Rendering (`packages/avatar`)

- `energy-figure.ts` samples anatomical head/torso proportions into deterministic light
  points. It contains no polygon character mesh or facial feature textures. A depth-only
  silhouette occludes background waves; it is never shaded as a surface.
- `energy-shaders.ts` draws additive light with raw WebGL 1. Incommensurate frequencies
  drive breathing, silhouette drift, particle flow and waves without a short loop.
  Listening adds restrained cyan attention; thinking converges waves and reorganizes
  facial scans; speaking warms the face from measured output audio; success/error/offline
  transition through controlled light states.
- Quality profiles: **auto**, **high**, **balanced**, **low**. Auto adapts draw density to
  measured frame time and starts low on small/dense/low-power devices. Low caps at 30 fps,
  balanced at 45 fps; DPR caps are 1×/1.5×/2×. A cheap glow pass is earned only after
  sustained fast frames and disabled again if the frame budget slips.
- Reduced motion (OS preference or the device setting) draws stills and pauses the loop.
  Hidden pages pause. Lost WebGL contexts recover. Without WebGL, a 2D canvas draws the
  same contour anatomy; there is no robot/orb fallback.

## Audio truthfulness

`level.ts` measures real PCM through an analyser. The web voice bus
(`apps/web/lib/voice/level.ts`) carries `{ level, channel, measured, status }`, so
microphone input can never drive the speaking face. Server-generated audio is measured
from the actual playback element; speaking starts on its `playing` event. Browser speech
synthesis exposes lifecycle events but no PCM tap: the UI reports **waveform unavailable**
and does not substitute a synthetic speech rhythm. Volume, speech rate and captions are
available in the voice drawer. Desktop and Android use the same channel-aware meter API.

## Camera attention (web, opt-in)

The camera is off by default and starts only after **Enable camera** is pressed.
`apps/web/lib/presence/face-worker.ts` loads the self-hosted MediaPipe runtime/model from
`/vision` (provenance and licenses: `apps/web/public/vision/README.md`). Inference runs in
a worker at a bounded 10 Hz on 256×192 video-only frames; only a smoothed head-pose
yaw/pitch leaves the worker. No landmarks, images, identity or emotion are uploaded or
persisted. `AttentionFilter` calibrates the first pose, applies a deadzone, rejects jumps
and expires stale detections. Stop, device removal, hidden page, page hide and unmount all
terminate the worker and stop every track. Permission/model failures release the camera
and fall back to pointer attention. A trusted embedding must also grant the iframe
`allow="camera"`; the app cannot grant that permission itself.

## Accessibility and controls

The web wrapper exposes one localized `role="img"` label and keeps the canvas decorative.
The voice stage is keyboard-operable; captions, quality, motion, light intensity, volume,
rate and camera consent are available in the voice drawer and device settings. Preferences
are device-local. Camera consent is never persisted. Uzbek, English and Russian strings
ship with the controls.

## Verification

- `pnpm --filter @ezo/avatar test`: 13 tests — deterministic geometry, light-family
  preservation, attention filtering, state mapping, real-level math and no-browser fallback.
- `pnpm --filter @ezo/web test`: 105 tests — signal provenance, security headers and
  existing app tests.
- `tests/e2e/specs/avatar-modes.spec.ts`: reduced-motion stills, power caps, context
  recovery, energy states and quality switching in Chromium.
- `tests/e2e/specs/avatar-performance.spec.ts`: point/DPR/heap budgets on the real voice
  stage; frame times are recorded, not presented as physical-device results.
- `tests/e2e/specs/voice*.spec.ts`: browser/server voice paths, actual playback start,
  barge-in and fallback with deterministic browser fixtures.
- Full Playwright suite (excluding the unpacked-extension spec): **87 passed, 3 skipped**
  on desktop/mobile/clap projects, including opt-in camera cleanup with a simulated
  video-only stream and measured server-audio provenance. The extension spec is excluded
  only because the sandbox Chromium aborts `chrome-extension://` navigation.

Software Chromium (SwiftShader) renders are software renders, not GPU benchmarks. Camera
and microphone hardware require a separate physical-device check; fake media streams in
tests prove wiring and cleanup only. The unpacked Chrome-extension Playwright spec needs
a full Chromium build with extension support; the sandbox's serverless Chromium aborts
`chrome-extension://` navigation, so that spec is reported separately rather than claimed
as passed.

## Origin and attribution

This is EZO's own procedural energy implementation. The public APEX-UI repository does
not contain the private reference humanoid. The optional SVG voice-frame pattern retains
its MIT attribution in `packages/avatar/NOTICE.md`; no APEX-UI character, shaders or assets
were copied. MediaPipe runtime/model licenses are vendored beside the self-hosted assets.
