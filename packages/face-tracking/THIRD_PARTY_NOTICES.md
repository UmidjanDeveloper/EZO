# Third-party attribution

EZO uses **MediaPipe Tasks Vision**, maintained by Google / google-ai-edge,
https://github.com/google-ai-edge/mediapipe, npm `@mediapipe/tasks-vision` **0.10.32**.
The SDK is Apache License 2.0. The unmodified upstream license is retained in
[licenses/MediaPipe-Apache-2.0.txt](licenses/MediaPipe-Apache-2.0.txt).
Upstream source/license review snapshot: `7c0ddec593580937fad5fcbcb792ad4fcbc3b67d`;
the installed binary SDK remains the independently pinned npm0.10.32 release,
not a build of that snapshot. Published package SRI is locked in pnpm-lock.yaml.

EZO adapters, attention logic and clap heuristics are new EZO code; no upstream
repository was copied. The permissioned example loads the existing EZO avatar.
The npm distribution includes JS/WASM runtime artifacts; retain upstream license,
copyright notices and required third-party notices when distributing those assets.
No separate NOTICE file appeared in the inspected npm tarball. This does not clear
all platform/model distribution obligations or constitute a model license review.

**No model weights are distributed here.** Face/hand weights have separate terms
and remain unapproved/unavailable in this environment. Before shipping, review
exact official model cards/licenses/security notices, pin downloaded SHA256 values,
and retain their required attribution/notices. Do not infer weight licensing from
the Apache SDK. See the integration contract's explicit model release gate.
