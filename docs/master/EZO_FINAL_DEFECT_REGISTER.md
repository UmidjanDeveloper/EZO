# EZO — final defect register

Every confirmed, reproducible defect found in the Ultimate Final Master Completion mission
(2026-10-27 →). One row per defect: SEVERITY → REPRODUCTION → ROOT CAUSE → FIX →
REGRESSION TEST → STATUS. Statuses: FIXED (with the commit/PR), OPEN, BLOCKED (owner or
infrastructure), WONTFIX (with the reason). Unconfirmed suspicions are listed separately
and never counted as defects. No percentages.

Severity: P0 security or data loss · P1 feature broken for the owner · P2 wrong but
recoverable · P3 cosmetic / docs.

## A. Perception integration (PR #57, found by the simulated-camera specs)

| ID | Sev | Reproduction | Root cause | Fix | Regression test | Status |
|---|---|---|---|---|---|---|
| D-001 | P1 | Web/Windows/Android: press the camera button with the bundled engine → "Kamera xatosi: Aborted(NetworkError: Failed to execute 'send' on 'XMLHttpRequest'…)" after ~2 s | The WASM runtime reads the SHA256-verified binary from a blob URL the worker made; `connect-src` had no `blob:` (`apps/web/lib/security-headers.ts`, `apps/desktop/src/renderer/pill.html`, worker response header in `apps/desktop/src/main/index.ts`) | `connect-src 'self' blob:` in all three; no remote host | `tests/e2e/specs/perception.spec.ts` (6 specs, project `perception`) | FIXED `201f98d` (PR #57) |
| D-002 | P2 | Pill from `file://` or a build without `/vision`: move the pointer over the figure → no "(kamera emas)" label; the figure still follows the pointer unlabelled | `MotionAdapter` existed only after the assets verified; fallback went straight to `setGaze` (`apps/desktop/src/renderer/pill.ts`, `apps/mobile/src/main.ts`, `apps/web/components/chat/CameraAttention.tsx`) | Adapter created with the figure; session added once verified | `desktop-pill.spec.ts` "ten times", `mobile-stage.spec.ts` (missing/tampered assets) | FIXED `201f98d` |
| D-003 | P2 | Slow machine (inference > 500 ms): Diagnostics "camera FPS 0, inference —" while the worker runs | Samples counted only for frames the controller accepted as fresh (`packages/perception-client/src/session.ts`) | Count every inference; freshness still governs attention | `perception.spec.ts` (`data-fps`, `data-inference-ms`) | FIXED `201f98d` |
| D-004 | P3 | Clap spec: provider "" after a mocked `/api/voice/speak` | Test double lacked `Access-Control-Expose-Headers`; the real API exposes `X-EZO-Voice-Provider` | Fixture fixed | `perception.spec.ts` | FIXED `201f98d` |
| D-005 | P2 | Android emulator (CI): "Vision deadline exceeded" at head `55c489e`; passed at `ce27a47` with the engine up after ≈17 s | Fixed 15 s timer for worker init and each frame in `packages/face-tracking/src/vision.ts` (engine, Codex); `nosimd` WASM only | Request 5/6 to Codex (configurable deadlines, SIMD pin); smoke records a start timeline | `tests/e2e/devices/android-smoke.mjs` | OPEN (engine) — flake risk, never skipped |
| D-006 | P2 | `pnpm --filter @ezo/web build` never finishes (Turbopack) with the engine in the graph | Engine's dead `import.meta.url` worker entry | `next build --webpack` | Web CI build | FIXED `55c489e` (workaround; request 1 to Codex) |

## B. Full-system audit (Stage 1–2)

_Rows are added as each finding is reproduced. A finding reported by an auditor but not
reproduced stays in §C._

| ID | Sev | Reproduction | Root cause | Fix | Regression test | Status |
|---|---|---|---|---|---|---|

## C. Unconfirmed suspicions (not defects until reproduced)

| ID | Area | Suspicion | Next step |
|---|---|---|---|
