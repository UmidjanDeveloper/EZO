import type { MotionAdapter, VisionStatus } from "@ezo/avatar";
import {
  AttentionController,
  CameraTracker,
  ClapDetector,
  ClapMicrophone,
  createVisionEstimator,
  type ClapDetected,
  type MicrophoneStatus,
  type MotionIntent,
  type PerceptionFrame,
  type TrackingStatus,
  type VisionAssets,
} from "@ezo/face-tracking";

export interface Diagnostics {
  /** Inference samples per second over the last second (0 when the camera is off). */
  cameraFps: number;
  /** Last worker inference time in ms (null when the camera is off). */
  inferenceMs: number | null;
  faceDetected: boolean;
  handDetected: boolean;
  attention: MotionIntent["state"];
  clapCount: number;
  camera: VisionStatus["camera"];
  microphone: MicrophoneStatus;
  lastError: string | null;
}

export interface SessionHost {
  /** Asset base on the app's own origin, e.g. "/vision/"; the bundled worker is `${base}vision.worker.js`. */
  base: string;
  assets: VisionAssets;
  video: HTMLVideoElement;
  /** The engine writes its own status words into these (keep them visible). */
  cameraIndicator: HTMLElement;
  microphoneIndicator: HTMLElement;
  adapter: MotionAdapter;
  lowPower?: boolean;
  reducedMotion?: boolean;
  /** The selfie camera is mirrored on screen, so the engine flips x by default. */
  mirrored?: boolean;
  onVision?: (status: VisionStatus) => void;
  onMicrophone?: (status: MicrophoneStatus, error?: string) => void;
  onClap?: (event: ClapDetected) => void;
  onDiagnostics?: (diagnostics: Diagnostics) => void;
}

/** Engine status words mapped to the UI's camera state; a refused permission reads as "denied". */
export function cameraState(status: TrackingStatus, error?: string): VisionStatus["camera"] {
  if (status === "error") return /denied|NotAllowed|permission/i.test(error ?? "") ? "denied" : "error";
  return status;
}

/**
 * One perception session for one stage, composed from the engine's own parts exactly as its
 * `HumanoidPerception` does (CameraTracker → worker estimator → AttentionController → the
 * figure's adapter; ClapMicrophone → ClapDetector), except that the worker is the app's
 * bundled `vision.worker.js` (the engine's `new URL(import.meta.url)` form cannot be bundled
 * by every app's build; see the Codex request in the PR). The engine's AttentionController
 * is the only attention state machine. Camera and clap microphone start only from the
 * owner's own clicks; hidden views stop both; `stop()` terminates the worker and releases
 * every track.
 */
export class PerceptionSession {
  readonly attention: AttentionController;
  private readonly host: SessionHost;
  private readonly camera: CameraTracker;
  private readonly microphone: ClapMicrophone;
  private vision: VisionStatus = { camera: "off", since: 0 };
  private microphoneStatus: MicrophoneStatus = "off";
  private samples: number[] = [];
  private inferenceMs: number | null = null;
  private intent: MotionIntent | null = null;
  private clapCount = 0;
  private lastError: string | null = null;
  private render: number | undefined;
  private active = false;
  private stopped = false;
  private readonly hide = () => {
    if (document.hidden) this.setVisible(false);
  };
  private readonly pagehide = () => this.stop();

  constructor(host: SessionHost) {
    this.host = host;
    this.attention = new AttentionController({ mirrored: host.mirrored ?? true, reducedMotion: host.reducedMotion });
    this.microphone = new ClapMicrophone({
      indicator: host.microphoneIndicator,
      detector: new ClapDetector(),
      onClap: (event) => {
        this.clapCount += 1;
        host.onClap?.(event);
        this.report();
      },
      onStatus: (status, error) => {
        if (error) this.lastError = error;
        this.microphoneStatus = status;
        host.onMicrophone?.(status, error);
        this.report();
      },
    });
    this.camera = new CameraTracker({
      video: host.video,
      indicator: host.cameraIndicator,
      lowPower: host.lowPower,
      createEstimator: (signal) =>
        createVisionEstimator(host.assets, (frame) => this.frame(frame), {
          signal,
          workerFactory: () => new Worker(`${host.base}vision.worker.js`),
          // Engine defaults: 60 s for initialization (fetch + SHA256 of 22 MB + WASM compile + two
          // model loads: ≈9 s on a laptop, 17–23 s on the CI Android emulator), 15 s per frame.
        }),
      onFrame: () => undefined,
      onStatus: (status, error) => {
        if (error) this.lastError = error;
        const camera = cameraState(status, error);
        if (status === "error") {
          this.stopRender();
          this.attention.reset();
          host.adapter.apply(this.attention.sample(performance.now()));
        }
        if (camera !== this.vision.camera) {
          this.vision = { camera, since: performance.now(), message: camera === "error" || camera === "denied" ? (error ?? this.lastError ?? undefined) : undefined };
          if (camera === "off") {
            this.samples = [];
            this.inferenceMs = null;
          }
          host.onVision?.(this.vision);
        }
        this.report();
      },
    });
  }

  private frame(frame: PerceptionFrame): void {
    if (!this.active) return;
    const now = performance.now();
    // Diagnostics count every inference, including frames the controller rejects as stale
    // (slower than its freshness budget): the owner must see "inference 900 ms" rather than nothing.
    this.inferenceMs = frame.inferenceMs;
    this.samples.push(frame.timestampMs);
    const floor = frame.timestampMs - 1000;
    while (this.samples.length && this.samples[0]! < floor) this.samples.shift();
    const fresh = this.attention.ingest(frame, now);
    if (fresh) this.microphone.detector.observeHands(frame.handsDistance, now);
    this.report();
  }

  private readonly tick = () => {
    if (!this.active) return;
    this.intent = this.attention.sample(performance.now());
    this.host.adapter.apply(this.intent);
    this.render = requestAnimationFrame(this.tick);
  };

  private stopRender(): void {
    if (this.render !== undefined) cancelAnimationFrame(this.render);
    this.render = undefined;
  }

  /** Permission action: bind to the camera button only. */
  async startCamera(): Promise<void> {
    if (this.stopped || document.hidden) return;
    this.lastError = null;
    this.active = true;
    document.addEventListener("visibilitychange", this.hide);
    globalThis.addEventListener("pagehide", this.pagehide);
    await this.camera.start();
    if (this.active && this.vision.camera !== "error" && this.vision.camera !== "denied" && this.render === undefined) this.tick();
  }

  stopCamera(): void {
    this.active = false;
    this.camera.stop();
    this.stopRender();
    this.attention.reset();
    this.intent = null;
    this.host.adapter.apply(this.attention.sample(performance.now()));
    document.removeEventListener("visibilitychange", this.hide);
    globalThis.removeEventListener("pagehide", this.pagehide);
  }

  /** Permission action: bind to the clap "Listen" button only (separate from the camera). */
  async startClap(): Promise<void> {
    if (this.stopped) return;
    this.lastError = null;
    await this.microphone.start();
  }

  stopClap(): void {
    this.microphone.stop();
  }

  /** While EZO listens or speaks, attention follows that mode and claps are suppressed while speaking. */
  setInteraction(mode: "listening" | "speaking" | null): void {
    this.attention.setInteraction(mode);
    this.microphone.setSuppressed(mode === "speaking");
  }

  /** Hidden/disabled view stops BOTH sensors; showing never silently restarts them. */
  setVisible(visible: boolean): void {
    this.camera.setVisible(visible);
    this.host.adapter.setVisible(visible);
    if (!visible) {
      this.stopCamera();
      this.stopClap();
      this.microphone.setSuppressed(false);
    }
  }

  /** Both sensors off, the worker terminated, the figure released. */
  stop(): void {
    this.stopped = true;
    this.stopCamera();
    this.stopClap();
    this.microphone.setSuppressed(false);
    this.host.adapter.stop();
    this.report();
  }

  visionStatus(): VisionStatus {
    return this.vision;
  }

  microphoneStatusNow(): MicrophoneStatus {
    return this.microphoneStatus;
  }

  diagnostics(): Diagnostics {
    return {
      cameraFps: this.vision.camera === "tracking" || this.vision.camera === "lost" ? this.samples.length : 0,
      inferenceMs: this.inferenceMs,
      faceDetected: this.intent?.source === "face",
      handDetected: this.intent?.source === "hand",
      attention: this.intent?.state ?? "neutral",
      clapCount: this.clapCount,
      camera: this.vision.camera,
      microphone: this.microphoneStatus,
      lastError: this.lastError,
    };
  }

  private report(): void {
    this.host.onDiagnostics?.(this.diagnostics());
  }
}
