import { ClapDetector } from "./clap";
import { ClapMicrophone, type MicrophoneStatus } from "./microphone";
import type { ClapDetected } from "./types";

export interface Diagnostics {
  clapCount: number;
  microphone: MicrophoneStatus;
  lastError: string | null;
}

export interface SessionHost {
  /** The engine writes its own status words into this (keep it visible). */
  microphoneIndicator: HTMLElement;
  onMicrophone?: (status: MicrophoneStatus, error?: string) => void;
  onClap?: (event: ClapDetected) => void;
  onDiagnostics?: (diagnostics: Diagnostics) => void;
}

/**
 * One clap session for one stage: the clap microphone (ClapMicrophone → ClapDetector).
 * It starts only from the owner's own press; a hidden view stops it; `stop()` releases
 * every track. Nothing is recorded or uploaded; a clap is an acknowledgement only.
 */
export class ClapSession {
  private readonly host: SessionHost;
  private readonly microphone: ClapMicrophone;
  private microphoneStatus: MicrophoneStatus = "off";
  private clapCount = 0;
  private lastError: string | null = null;
  private stopped = false;

  constructor(host: SessionHost) {
    this.host = host;
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
  }

  /** Permission action: bind to the clap "Listen" button only. */
  async startClap(): Promise<void> {
    if (this.stopped) return;
    this.lastError = null;
    await this.microphone.start();
  }

  stopClap(): void {
    this.microphone.stop();
  }

  /** Claps are ignored while EZO speaks (its own voice must not trigger one). */
  setInteraction(mode: "listening" | "speaking" | null): void {
    this.microphone.setSuppressed(mode === "speaking");
  }

  /** A hidden view stops the microphone; showing never silently restarts it. */
  setVisible(visible: boolean): void {
    if (!visible) {
      this.stopClap();
      this.microphone.setSuppressed(false);
    }
  }

  stop(): void {
    this.stopped = true;
    this.stopClap();
    this.microphone.setSuppressed(false);
    this.report();
  }

  microphoneStatusNow(): MicrophoneStatus {
    return this.microphoneStatus;
  }

  diagnostics(): Diagnostics {
    return { clapCount: this.clapCount, microphone: this.microphoneStatus, lastError: this.lastError };
  }

  private report(): void {
    this.host.onDiagnostics?.(this.diagnostics());
  }
}
