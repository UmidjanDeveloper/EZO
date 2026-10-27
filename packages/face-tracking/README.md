# EZO humanoid perception SDK

Independent sensing SDK for the **existing** EZO avatar. Camera and microphone OFF
by default, separate explicit activation, local ephemeral processing, no recordings
or identity recognition. It reuses CameraTracker and existing avatar.setGaze.

Implemented: async permissioned camera lifecycle, pinned MediaPipe0.10.32 CPU WASM
worker adapter, face/hand result conversion, normalized hand motion, deterministic
attention, smoothing/dwell/expiry, local AudioWorklet clap heuristics, UZ/EN/RU
acknowledgement intents and provider-independent actual-playback contract.

**PARTIAL/BLOCKED:** official face/hand weights could not be downloaded (policy403);
model-card/license/hash approval, successful live landmark inference, real hardware,
shipping-client integration and heard provider speech are unverified. No synthetic
signal is presented as real perception. The integrated permissioned example uses
actual existing EzoAvatar, no fake-frame fallback, and honest voice-unavailable state.

```sh
pnpm --filter @ezo/face-tracking typecheck
pnpm --filter @ezo/face-tracking test
pnpm --filter @ezo/face-tracking test:browser # Playwright Chromium installed first; fake-media simulation
pnpm --filter @ezo/face-tracking build:acceptance
```

After approved assets are prepared, `pnpm --filter @ezo/face-tracking acceptance`
builds and serves localhost8099. No remote host or sensor starts automatically.
See [the API/Claude handoff](../../docs/devices/HUMANOID_PERCEPTION_CONTRACT.md),
[camera/model/hardware checks](../../docs/devices/CAMERA_GESTURE_ACCEPTANCE.md),
[clap/voice checks](../../docs/devices/CLAP_VOICE_ACCEPTANCE.md),
[validation](VALIDATION.md) and [third-party notices](THIRD_PARTY_NOTICES.md).

Consumers must implement visible indicators/stop buttons, safe callbacks, unmount/
hide cleanup, appropriate OS permission and reviewed CSP/bundler integration.
No existing desktop/mobile/web/avatar/provider implementations are changed here.
