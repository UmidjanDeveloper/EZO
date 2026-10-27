/**
 * Sensing contract between EZO's surfaces (web, Windows, Android) and the sensing engine
 * (packages/face-tracking today; hand, gesture and clap recognition as they land).
 *
 * The engine produces the frames and events below; the surfaces consume them through
 * `AttentionDriver`, which decides where the humanoid looks and never trusts a frame that
 * is stale, low-confidence, or arrived while the view was hidden. Everything is structural
 * TypeScript: no runtime dependency in either direction. All angles/positions are
 * normalised -1..1 (left/down negative … right/up positive) as the *user* sees them, so a
 * hand on the user's right makes EZO look to the user's right. Nothing here identifies a
 * person: there is no face identity, no biometrics, no recording.
 */
import type { Gaze } from "./avatar";

/** One head-tracking frame (identical in shape to packages/face-tracking's TrackingFrame). */
export interface TrackingFrame {
  yaw: number;
  pitch: number;
  roll: number;
  /** Where the face sits in the camera view, not calibrated eye tracking. */
  gazeX: number;
  gazeY: number;
  /** 1 = a single model-accepted face; below `minConfidence` the frame is ignored. */
  confidence: number;
  /** Monotonic browser milliseconds (performance.now()). */
  timestamp: number;
}

export interface HeadPose {
  yaw: number;
  pitch: number;
  roll: number;
  confidence: number;
  timestamp: number;
}

/** A hand the engine is confident about; EZO looks towards it while it is raised. */
export interface HandTarget {
  /** Hand centre in the user's view, -1..1. */
  x: number;
  y: number;
  hand: "left" | "right" | "unknown";
  /** True while the hand is held up (wrist below the fingers); a resting hand is not a target. */
  raised: boolean;
  confidence: number;
  timestamp: number;
}

/** What the driver decided for this moment, for the UI and for tests. */
export type MotionIntent =
  | { kind: "look"; target: Gaze; source: "head" | "hand" | "pointer" | "touch"; confidence: number }
  | { kind: "rest"; source: "stale" | "hidden" | "stopped" | "none" | "low-confidence" | "camera-off" };

/** A verified clap (the engine owns the audio/visual verification; this is only the result). */
export interface ClapEvent {
  timestamp: number;
  confidence: number;
  /** One clap or a double clap. */
  count: 1 | 2;
}

export type CameraState = "off" | "requesting" | "denied" | "unavailable" | "tracking" | "lost" | "error";

/** Truthful camera status for the UI: it mirrors the OS/browser permission, never guesses. */
export interface VisionStatus {
  camera: CameraState;
  faces: 0 | 1;
  hands: number;
  /** Set when the status comes from a test fixture rather than a device. */
  simulated?: boolean;
  message?: string;
  since: number;
}

/** Spoken intents the voice pipeline recognised (the provider owns recognition). */
export interface VoiceIntent {
  kind: "wake" | "stop" | "confirm" | "cancel";
  transcript?: string;
  language?: "uz" | "en" | "ru";
  confidence: number;
  timestamp: number;
}

/** The part of EzoAvatar the driver needs. */
export interface GazeTarget {
  setGaze(gaze: Gaze | null): void;
}

export interface AttentionOptions {
  /** A sensor frame older than this is ignored (default 400 ms). */
  staleMs?: number;
  /** Frames below this confidence are ignored (default 0.5). */
  minConfidence?: number;
  /** Changes smaller than this (in -1..1 units) do not move the target: no jitter (default 0.03). */
  deadband?: number;
  /** A raised hand keeps priority over the head for this long after its last frame (default 1200 ms). */
  handHoldMs?: number;
  /** Clock, replaceable in tests. */
  now?: () => number;
  /** Called whenever the intent changes kind or source. */
  onIntent?: (intent: MotionIntent) => void;
}

/**
 * Turns sensing frames into one gaze for the humanoid.
 *
 * Priority: a raised hand → the head → the pointer/touch fallback → rest. Sensor frames
 * only count while the camera reports tracking and the view is visible; `tick()` must be
 * called regularly (the host's animation frame) so stale frames release the gaze.
 */
export class AttentionDriver {
  private readonly target: GazeTarget;
  private readonly staleMs: number;
  private readonly minConfidence: number;
  private readonly deadband: number;
  private readonly handHoldMs: number;
  private readonly clock: () => number;
  private readonly onIntent: ((intent: MotionIntent) => void) | null;
  private head: TrackingFrame | HeadPose | null = null;
  private hand: HandTarget | null = null;
  private pointer: { gaze: Gaze; source: "pointer" | "touch" } | null = null;
  private vision: VisionStatus = { camera: "off", faces: 0, hands: 0, since: 0 };
  private visible = true;
  private stopped = false;
  private current: MotionIntent = { kind: "rest", source: "none" };
  private applied: Gaze | null = null;

  constructor(target: GazeTarget, options: AttentionOptions = {}) {
    this.target = target;
    this.staleMs = options.staleMs ?? 400;
    this.minConfidence = options.minConfidence ?? 0.5;
    this.deadband = options.deadband ?? 0.03;
    this.handHoldMs = options.handHoldMs ?? 1200;
    this.clock = options.now ?? (() => (typeof performance !== "undefined" ? performance.now() : Date.now()));
    this.onIntent = options.onIntent ?? null;
  }

  /** The engine's camera status; sensor frames are ignored unless it is "tracking". */
  setVision(status: VisionStatus): void {
    this.vision = status;
    if (status.camera !== "tracking") {
      this.head = null;
      this.hand = null;
    }
    this.tick();
  }

  getVision(): VisionStatus {
    return this.vision;
  }

  /** A head frame from the engine (null = no face this frame). */
  headFrame(frame: TrackingFrame | HeadPose | null): void {
    this.head = frame && this.accept(frame.confidence, frame.timestamp) ? frame : null;
    this.tick();
  }

  /** A hand frame from the engine (null = no hand this frame). */
  handFrame(hand: HandTarget | null): void {
    this.hand = hand && hand.raised && this.accept(hand.confidence, hand.timestamp) ? hand : null;
    this.tick();
  }

  /** Pointer/touch fallback (labelled as such in the intent); null when the pointer leaves. */
  pointerGaze(gaze: Gaze | null, source: "pointer" | "touch" = "pointer"): void {
    this.pointer = gaze ? { gaze, source } : null;
    this.tick();
  }

  /** Hidden views never track: frames arriving while hidden are dropped. */
  setVisible(visible: boolean): void {
    this.visible = visible;
    if (!visible) {
      this.head = null;
      this.hand = null;
    }
    this.tick();
  }

  /** Releases the gaze and ignores everything until frames arrive again. */
  stop(): void {
    this.stopped = true;
    this.head = null;
    this.hand = null;
    this.pointer = null;
    this.tick();
    this.stopped = false;
  }

  intent(): MotionIntent {
    return this.current;
  }

  /** Re-evaluates with the clock: call every animation frame so stale frames let go. */
  tick(): void {
    const next = this.decide();
    const gaze = next.kind === "look" ? next.target : null;
    const moved =
      (gaze === null) !== (this.applied === null) ||
      (gaze && this.applied && (Math.abs(gaze.yaw - this.applied.yaw) > this.deadband || Math.abs(gaze.pitch - this.applied.pitch) > this.deadband));
    if (moved) {
      this.applied = gaze ? { ...gaze } : null;
      this.target.setGaze(this.applied);
    }
    if (next.kind !== this.current.kind || next.source !== this.current.source) {
      this.current = next;
      this.onIntent?.(next);
    } else if (next.kind === "look" && this.current.kind === "look") {
      this.current = next;
    }
  }

  private accept(confidence: number, timestamp: number): boolean {
    return Number.isFinite(confidence) && confidence >= this.minConfidence && Number.isFinite(timestamp) && this.clock() - timestamp <= this.staleMs;
  }

  private decide(): MotionIntent {
    if (this.stopped) return { kind: "rest", source: "stopped" };
    if (!this.visible) return { kind: "rest", source: "hidden" };
    const now = this.clock();
    if (this.vision.camera === "tracking") {
      if (this.hand && now - this.hand.timestamp <= this.handHoldMs) {
        return { kind: "look", target: { yaw: clamp1(this.hand.x), pitch: clamp1(this.hand.y) }, source: "hand", confidence: this.hand.confidence };
      }
      if (this.head) {
        if (now - this.head.timestamp > this.staleMs) {
          this.head = null;
          return this.fallback("stale");
        }
        // The face position says where the person is; the head angles say where they turned.
        const frame = this.head as Partial<TrackingFrame>;
        const yaw = typeof frame.gazeX === "number" ? frame.gazeX : this.head.yaw;
        const pitch = typeof frame.gazeY === "number" ? frame.gazeY : this.head.pitch;
        return { kind: "look", target: { yaw: clamp1(yaw), pitch: clamp1(pitch) }, source: "head", confidence: this.head.confidence };
      }
      return this.fallback("none");
    }
    return this.fallback(this.vision.camera === "off" ? "none" : "camera-off");
  }

  private fallback(reason: "stale" | "none" | "camera-off"): MotionIntent {
    if (this.pointer) return { kind: "look", target: this.pointer.gaze, source: this.pointer.source, confidence: 1 };
    return { kind: "rest", source: reason };
  }
}

function clamp1(v: number): number {
  return Math.min(1, Math.max(-1, Number.isFinite(v) ? v : 0));
}
