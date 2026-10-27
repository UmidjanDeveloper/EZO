# EZO — final integration report: PR #57 ↔ PR #58 and the canonical perception architecture

Date: 2026-10-27. Statuses are COMPLETE / PARTIAL / BLOCKED / NOT STARTED and describe
verified evidence, not the existence of files. No completion percentages.

## 1. State of the two pull requests

| PR | Branch | Owner | State | Head | What it holds |
|---|---|---|---|---|---|
| [#58](https://github.com/UmidjanDeveloper/EZO/pull/58) | `feat/humanoid-perception` | Codex | **MERGED** into `claude/gifted-goodall-bpf01s` (merge `1e47ca0`) | `9a75c92` | The perception engine only: `packages/face-tracking` (MediaPipe Tasks Vision in a worker, `AttentionController`, `ClapMicrophone`/`ClapDetector`, `VoiceReaction`, asset pins and SHA256 verification), its tests (54), docs `docs/devices/HUMANOID_PERCEPTION_CONTRACT.md`, `CAMERA_GESTURE_ACCEPTANCE.md`, `CLAP_VOICE_ACCEPTANCE.md`, workflow changes for that package. No app is wired. |
| [#57](https://github.com/UmidjanDeveloper/EZO/pull/57) | `section-c/perception-voice` | Claude | **OPEN**, built on the merged #56 and on #58 (the branch now contains `1e47ca0`, merged without conflicts) | see the PR | Wiring of that engine into web, Windows and Android (`@ezo/perception-client`, bundled verified assets, CSP, permissions, lifecycle), clap → spoken acknowledgement through the real `/api/voice/speak`, ElevenLabs per-language voices, the owner test kit (Diagnostics pages, artifacts, `EZO_OWNER_TEST_UZ.md`). The only change to `packages/face-tracking/**` is the additive deadline option in `vision.ts` (+ its test), made after #58 merged and flagged for Codex. |

There is no overlap in files between the two PRs after the merge: #58 owns
`packages/face-tracking/**` and its docs; #57 touches only consumers. The former duplicate
(`AttentionDriver` in `packages/avatar`) was deleted in #57 — see §2.

Build-order dependency: #57 must be merged **after** #58 (already satisfied: #58 is in the
integration branch and in #57's history). Merging is the owner's decision.

## 2. Canonical perception architecture (one engine, one adapter, one renderer)

```
owner's click ──▶ CameraTracker ──▶ vision.worker.js (MediaPipe, CPU) ──▶ PerceptionFrame
 (packages/face-tracking)                 │ assets: /vision/* on the app origin,
                                          │ SHA256-verified, nothing fetched remotely
                                          ▼
                                   AttentionController  ──▶ MotionIntent
                                   (packages/face-tracking)      │
                                                                 ▼
                                   MotionAdapter (packages/avatar/src/sensing.ts)
                                   engine first; labelled pointer/touch fallback when neutral
                                                                 │
                                                                 ▼
                                   EzoAvatar.setGaze / setLevel (packages/avatar, render only)

owner's click ──▶ ClapMicrophone (AudioWorklet) ──▶ ClapDetector ──▶ acknowledgement()
                                                                      │
                               VoiceReaction ──▶ AcknowledgementSpeaker (perception-client)
                                                 real /api/voice/speak, real <audio>, measured level
```

| Layer | Package | Role | Rule |
|---|---|---|---|
| Engine | `packages/face-tracking` (Codex) | Camera/microphone capture, inference worker, attention state machine, clap detection, acknowledgement intent | The **only** perception state machine. Consumers never re-implement hand/head/stale logic. |
| Adapter | `packages/perception-client` (`PerceptionSession`, `AcknowledgementSpeaker`, `loadVisionAssets`, `Diagnostics`) | Composes the engine's parts exactly as its `HumanoidPerception` does, with the app's bundled worker; maps engine status words to the UI's `VisionStatus`; counts diagnostics; plays the acknowledgement through the app's authenticated TTS | Thin. No inference, no thresholds, no biometric storage. Exists only because the engine's `HumanoidPerception` hard-codes `new Worker(new URL('./vision.worker.ts', import.meta.url))`, which esbuild (Windows) cannot bundle (request 1 to Codex). |
| Presentation | `packages/avatar` (`MotionAdapter`, `EzoAvatar`) | Applies `MotionIntent` to the figure; labelled pointer/touch fallback; releases the gaze when hidden/stopped; renders | Never decides attention. `AttentionDriver` (Section B) **deleted** in #57. |
| Apps | `apps/web`, `apps/desktop`, `apps/mobile` | Consent UI, indicators, settings, Diagnostics, lifecycle hooks (hidden/background/quit/revocation) | Camera and clap start only from the owner's own clicks; hidden views stop both; nothing restarts by itself. |

Versioned contract: the adapter mirrors the engine's `MotionIntent`/`AttentionState` structurally
(`packages/avatar/src/sensing.ts`) so the packages do not depend on each other; a change in the
engine's shape fails `packages/perception-client` typecheck and `packages/avatar` tests.

## 3. Defects found while integrating (all fixed in #57)

| # | Defect | Root cause | Fix | Regression test |
|---|---|---|---|---|
| I1 | The engine died at start on all three clients: "Aborted(NetworkError: Failed to execute 'send' on 'XMLHttpRequest': Failed to load 'blob:…')" | The WASM runtime fetches the SHA256-verified binary through a blob URL the worker created; `connect-src` had no `blob:` source (web CSP, Windows pill meta, `vision.worker.js` response header) | `connect-src 'self' blob:` in all three places; still no remote host | `tests/e2e/specs/perception.spec.ts` (project `perception`, fake camera) on web, Windows pill dist and Android dist |
| I2 | Pointer/touch fallback had no label without the engine (file:// pill, builds without assets) | The `MotionAdapter` was created only when the assets verified | Adapter is created with the figure on every client; the engine session is added once the bundle verified | `desktop-pill.spec.ts` ("ten times"), `mobile-stage.spec.ts` |
| I3 | Diagnostics showed 0 FPS on a slow machine although the worker ran | Samples were counted only for frames the controller accepted as fresh (≤500 ms) | Count every inference; freshness still governs attention | `perception.spec.ts` (`data-fps > 0`, `data-inference-ms > 0`) |
| I4 | Web clap acknowledgement reported no provider | Test double lacked `Access-Control-Expose-Headers`; the real API exposes `X-EZO-Voice-Provider` (`apps/api/src/ezo_api/main.py`) | Fixture fixed; production unchanged | `perception.spec.ts` (`data-tts-provider`) |
| I5 | Android emulator: "Vision deadline exceeded" at `55c489e` and `7776d42` (engine up after 23 s), passed once at `ce27a47` (≈17 s, 1.2 s per inference) | The engine's fixed 15 s timer for worker initialisation and for each frame (`packages/face-tracking/src/vision.ts`), `nosimd` WASM only | **Additive engine option** `initTimeoutMs`/`frameTimeoutMs` (default unchanged, bounded 1–120 s, 3 unit tests) — the one change to `packages/face-tracking` in #57, after #58 merged, flagged for Codex's review; `PerceptionSession` passes 60 s for initialisation. The smoke records a start timeline. SIMD pin stays request 6 | `packages/face-tracking/src/vision.deadline.test.ts`, `tests/e2e/devices/android-smoke.mjs` |
| I6 | Next 16.4 Turbopack never finishes with the engine in the module graph | The engine's dead `import.meta.url` worker entry | Production build uses `next build --webpack` (documented in `next.config.ts`) | Web CI build |

## 4. Evidence by category (never interchangeable)

| Category | Evidence | Status |
|---|---|---|
| GREEN on hosted CI | Head `ce27a47`: Web (lint, types, unit, build, Playwright 94/94 incl. `perception`), Windows installer + real-OS self-test, Android APK build, Security (gitleaks, pip-audit, pnpm audit, Trivy), Docker; API job see the PR status comment | COMPLETE for that head |
| VERIFIED on Windows CI runner | Installer builds and installs; the pill's engine path runs only in Chromium (Playwright) from `dist/`, not in the installed Electron on the runner | PARTIAL |
| VERIFIED on Android emulator | Real APK, `CAMERA` granted, camera button pressed, engine up, state "lost" (synthetic scene has no face), 1 fps, inference 1.2 s | PARTIAL (SIMULATION) |
| VERIFIED with a mocked provider | Clap → `/api/voice/speak` (mocked) → real playback → cache → honest "unavailable" without a provider | COMPLETE (mock) |
| VERIFIED on the owner's physical device | — | **BLOCKED**: owner runs `docs/master/EZO_OWNER_TEST_UZ.md` and pastes the Diagnostics report |
| VERIFIED with a live paid provider | — | **BLOCKED**: `OPENAI_API_KEY` / `ELEVENLABS_API_KEY` on the owner's server |

## 5. Open requests to Codex (`packages/face-tracking`)

1. `workerFactory` / `workerUrl` option on `HumanoidPerception` (then `PerceptionSession` shrinks further).
2. `validateAssets`: allow an app scheme besides `https?:` (drops the `https://ezo.desktop` intercept on Windows).
3. Microphone level callback for Diagnostics.
4. Machine-readable error codes in `onStatus`.
5. Review the additive `initTimeoutMs`/`frameTimeoutMs` option added in #57 (default unchanged); consider exposing `maxAgeMs` tuning for slow devices.
6. SIMD WASM pin with feature detection.

## 6. Remaining risks

- Engine initialisation on the CI emulator takes 17–23 s (nosimd WASM on CPU); the session now
  allows 60 s. A real slow phone shows the same cost once per camera start; the SIMD pin (request 6)
  is the real remedy.
- Model licence: Apache-2.0 per Google's model cards, not re-fetched from this container;
  owner confirmation box in `scripts/vision/MODEL_LICENSE_REVIEW.txt`.
- Uzbek TTS through ElevenLabs stays off until the owner verifies the provider's Uzbek support
  (`EZO_ELEVENLABS_TTS_LANGUAGES`).
