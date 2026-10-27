/**
 * Build-time stand-in for `@mediapipe/tasks-vision` inside the perception engine's own
 * worker entry. The web app never runs that entry: it serves the engine's worker pre-bundled
 * at /vision/vision.worker.js (scripts/vision-assets.mjs) and passes it through
 * `workerFactory`. Turbopack still follows the engine's `new Worker(new URL(...))` and would
 * otherwise pull the 1 MB MediaPipe bundle into a worker chunk nobody loads (and hang on it).
 */
export const FaceLandmarker = undefined;
export const HandLandmarker = undefined;
