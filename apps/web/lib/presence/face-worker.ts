/// <reference lib="webworker" />
import { FaceLandmarker, FilesetResolver } from "@mediapipe/tasks-vision";

// All inference is local. Frames arrive as transferable ImageBitmaps, never network requests.
let landmarker: FaceLandmarker | null = null;
let closed = false;
const scope = self as unknown as DedicatedWorkerGlobalScope;
scope.onmessage = async (event: MessageEvent<{ type: "init" | "frame"; bitmap?: ImageBitmap; timestamp?: number }>) => {
  const { type, bitmap, timestamp } = event.data;
  try {
    if (type === "init") {
      const files = await FilesetResolver.forVisionTasks("/vision/wasm");
      if (closed) return;
      landmarker = await FaceLandmarker.createFromOptions(files, {
        baseOptions: { modelAssetPath: "/vision/face_landmarker.task", delegate: "CPU" },
        runningMode: "VIDEO", numFaces: 1,
        outputFacialTransformationMatrixes: true,
        minFaceDetectionConfidence: 0.6, minFacePresenceConfidence: 0.6, minTrackingConfidence: 0.6,
      });
      if (closed) { landmarker.close(); landmarker = null; return; }
      scope.postMessage({ type: "ready" });
      return;
    }
    if (type === "frame" && bitmap && landmarker && !closed) {
      const result = landmarker.detectForVideo(bitmap, timestamp ?? 0);
      const matrix = result.facialTransformationMatrixes[0]?.data;
      if (matrix && matrix.length === 16) {
        // Column-major rotation; only yaw/pitch leave the worker. No landmarks or images.
        const yaw = Math.atan2(matrix[8]!, matrix[10]!);
        const pitch = Math.atan2(-matrix[9]!, Math.hypot(matrix[8]!, matrix[10]!));
        scope.postMessage({ type: "attention", yaw: -yaw, pitch, found: true });
      } else scope.postMessage({ type: "attention", found: false });
    }
  } catch {
    scope.postMessage({ type: "error", code: "tracking" });
  } finally { bitmap?.close(); }
};
scope.addEventListener("close", () => { closed = true; landmarker?.close(); landmarker = null; });
