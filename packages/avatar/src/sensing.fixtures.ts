/**
 * SIMULATED engine output for tests and demos only. Every value is invented; nothing here
 * is a measurement of a camera, a face or a hand, and no test using these proves physical
 * camera behaviour. The `simulated: true` flag travels with the status so a UI can say so.
 */
import type { MotionIntent, VisionStatus } from "./sensing";

export function simulatedVision(camera: VisionStatus["camera"], at = 0): VisionStatus {
  return { camera, since: at, simulated: true, message: "simulated" };
}

/** An engine intent as `AttentionController.sample()` would produce it. */
export function simulatedIntent(source: MotionIntent["source"], yaw: number, pitch: number, at: number, state?: MotionIntent["state"]): MotionIntent {
  const fallback: MotionIntent["state"] = source === "neutral" ? "neutral" : source === "hand" ? "hand_attention" : "face_attention";
  return { source, yaw, pitch, roll: 0, confidence: source === "neutral" ? 0 : 0.8, timestampMs: at, state: state ?? fallback };
}
