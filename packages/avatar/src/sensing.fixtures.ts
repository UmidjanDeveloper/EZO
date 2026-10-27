/**
 * SIMULATED sensing events for tests and demos only. Every value is invented; nothing here
 * is a measurement of a camera, a face or a hand, and no test using these proves physical
 * camera behaviour. The `simulated: true` flag travels with the status so a UI can say so.
 */
import type { ClapEvent, HandTarget, TrackingFrame, VisionStatus } from "./sensing";

export function simulatedVision(camera: VisionStatus["camera"], at = 0, faces: 0 | 1 = camera === "tracking" ? 1 : 0, hands = 0): VisionStatus {
  return { camera, faces, hands, since: at, simulated: true, message: "simulated" };
}

/** A face slowly turning left-right; yaw/pitch and the face position agree. */
export function simulatedHeadFrame(at: number, phase = 0, confidence = 1): TrackingFrame {
  const yaw = 0.6 * Math.sin(phase);
  const pitch = 0.2 * Math.cos(phase * 0.7);
  return { yaw, pitch, roll: 0, gazeX: yaw, gazeY: pitch, confidence, timestamp: at };
}

export function simulatedHand(at: number, x: number, y: number, raised = true, confidence = 0.9): HandTarget {
  return { x, y, hand: "right", raised, confidence, timestamp: at };
}

export function simulatedClap(at: number, count: 1 | 2 = 1): ClapEvent {
  return { timestamp: at, confidence: 0.95, count };
}
