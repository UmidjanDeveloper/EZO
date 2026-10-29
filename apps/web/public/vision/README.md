# Self-hosted face attention runtime

These files are loaded only after the user explicitly enables **Camera attention**.
They are served from this origin; camera frames never go to a third-party CDN.

- `face_landmarker.task`: MediaPipe Face Landmarker float16 v1, 3,758,596 bytes.
  SHA-256: `64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff`.
  Source model: https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task
  Model terms: `MODEL-LICENSE.txt`.
- `wasm/`: `@mediapipe/tasks-vision@0.10.32` SIMD and non-SIMD runtimes.
  Package source: https://github.com/google-ai-edge/mediapipe
  Runtime license: `MEDIAPIPE-LICENSE.txt` (Apache-2.0); package notes: `MEDIAPIPE-README.md`.

The worker computes one face's head-pose transform on the CPU, then releases each
ImageBitmap. Only smoothed yaw/pitch reach the renderer. No identity, emotion,
landmarks, recording, upload or persisted camera consent is produced.
