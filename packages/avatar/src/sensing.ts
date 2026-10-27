/**
 * How EZO's figure consumes the perception engine (`@ezo/face-tracking`, owned separately).
 *
 * Decision (Section C): there is ONE attention state machine, the engine's
 * `AttentionController`, which arbitrates face/hand/explicit-mode and smooths the target.
 * This module no longer arbitrates anything. `MotionAdapter` applies the engine's
 * `MotionIntent` to the figure, adds the labelled pointer/touch fallback when the engine
 * has nothing (`source: "neutral"`), and guarantees that a hidden view or `stop()` releases
 * the gaze. Types below are structural mirrors of the engine's (no package dependency in
 * either direction), so the avatar package stays framework- and engine-free.
 * Nothing here identifies a person: no face identity, no biometrics, no recording.
 */
import type { Gaze } from "./avatar";

/** Mirror of the engine's `MotionIntent` (packages/face-tracking/src/types.ts). */
export type AttentionState = "neutral" | "face_attention" | "hand_attention" | "following_head" | "listening" | "speaking" | "attention_lost";
export interface MotionIntent {
  source: "face" | "hand" | "eye" | "neutral";
  yaw: number;
  pitch: number;
  roll: number;
  confidence: number;
  timestampMs: number;
  state: AttentionState;
}

export type CameraState = "off" | "requesting" | "denied" | "unavailable" | "tracking" | "lost" | "error";

/** Truthful camera status for the UI: it mirrors the engine/OS, never guesses. */
export interface VisionStatus {
  camera: CameraState;
  /** Set when the status comes from a test fixture rather than a device. */
  simulated?: boolean;
  message?: string;
  since: number;
}

/** What drives the gaze right now, for the words on screen and for tests. */
export interface AttentionView {
  source: "face" | "hand" | "pointer" | "touch" | "none";
  state: AttentionState | "hidden" | "stopped";
  confidence: number;
}

/** The part of EzoAvatar the adapter needs. */
export interface GazeTarget {
  setGaze(gaze: Gaze | null): void;
}

export interface MotionAdapterOptions {
  /** Called whenever the source or state changes (not on every frame). */
  onChange?: (view: AttentionView) => void;
}

const REST: AttentionView = { source: "none", state: "neutral", confidence: 0 };

/**
 * Applies the engine's intent to the figure. Engine first; when the engine says
 * "neutral", the pointer/touch fallback (labelled as such); otherwise rest.
 */
export class MotionAdapter {
  private readonly target: GazeTarget;
  private readonly onChange: ((view: AttentionView) => void) | null;
  private engine: MotionIntent | null = null;
  private pointer: { gaze: Gaze; source: "pointer" | "touch" } | null = null;
  private visible = true;
  private stopped = false;
  private applied: Gaze | null = null;
  private current: AttentionView = REST;

  constructor(target: GazeTarget, options: MotionAdapterOptions = {}) {
    this.target = target;
    this.onChange = options.onChange ?? null;
  }

  /** The engine's sample for this frame (HumanoidPerception.onMotionIntent). */
  apply(intent: MotionIntent): void {
    this.stopped = false;
    this.engine = intent;
    this.update();
  }

  /** Pointer/touch fallback; null when the pointer leaves. */
  pointerGaze(gaze: Gaze | null, source: "pointer" | "touch" = "pointer"): void {
    this.pointer = gaze ? { gaze, source } : null;
    this.update();
  }

  /** Hidden views never move the figure; the engine stops itself when hidden. */
  setVisible(visible: boolean): void {
    this.visible = visible;
    if (!visible) this.engine = null;
    this.update();
  }

  /** Releases the gaze; the next engine intent resumes. */
  stop(): void {
    this.stopped = true;
    this.engine = null;
    this.pointer = null;
    this.update();
  }

  view(): AttentionView {
    return this.current;
  }

  private update(): void {
    const next = this.decide();
    const gaze = next.gaze;
    const moved = (gaze === null) !== (this.applied === null) || (gaze && this.applied && (Math.abs(gaze.yaw - this.applied.yaw) > 0.004 || Math.abs(gaze.pitch - this.applied.pitch) > 0.004));
    if (moved) {
      this.applied = gaze ? { ...gaze } : null;
      this.target.setGaze(this.applied);
    }
    if (next.view.source !== this.current.source || next.view.state !== this.current.state) {
      this.current = next.view;
      this.onChange?.(next.view);
    } else this.current = next.view;
  }

  private decide(): { gaze: Gaze | null; view: AttentionView } {
    if (this.stopped) return { gaze: null, view: { source: "none", state: "stopped", confidence: 0 } };
    if (!this.visible) return { gaze: null, view: { source: "none", state: "hidden", confidence: 0 } };
    const engine = this.engine;
    if (engine && engine.source !== "neutral") {
      return {
        gaze: { yaw: clamp1(engine.yaw), pitch: clamp1(engine.pitch) },
        view: { source: engine.source === "eye" ? "face" : engine.source, state: engine.state, confidence: clamp1(engine.confidence) },
      };
    }
    if (this.pointer) return { gaze: this.pointer.gaze, view: { source: this.pointer.source, state: engine?.state ?? "neutral", confidence: 1 } };
    return { gaze: null, view: { source: "none", state: engine?.state ?? "neutral", confidence: 0 } };
  }
}

function clamp1(v: number): number {
  return Math.min(1, Math.max(-1, Number.isFinite(v) ? v : 0));
}
