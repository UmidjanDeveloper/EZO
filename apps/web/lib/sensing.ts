/**
 * Where the camera/gesture sensing engine plugs into the web app (same shape as the
 * Windows app's slot). The engine — packages/face-tracking and the hand/clap work, owned
 * separately — provides `start()`; the voice stage consumes frames through @ezo/avatar's
 * AttentionDriver and never opens the camera itself. No provider is bundled in this build,
 * so the control is disabled and says so. A test may install a SIMULATED provider on
 * `window.ezoSensingProvider`; the stage labels it as simulated on screen.
 */
import type { ClapEvent, HandTarget, TrackingFrame, VisionStatus } from "@ezo/avatar";

export interface SensingSession {
  /** Stops capture immediately: every track ends, nothing is retained. */
  stop(): void;
}

export interface SensingProvider {
  /** Set by test fixtures only; a real engine never claims this. */
  simulated?: boolean;
  start(options: {
    video: HTMLVideoElement;
    onStatus: (status: VisionStatus) => void;
    onHead: (frame: TrackingFrame | null) => void;
    onHand?: (hand: HandTarget | null) => void;
    onClap?: (clap: ClapEvent) => void;
  }): Promise<SensingSession>;
}

export function sensingProvider(): SensingProvider | null {
  if (typeof window === "undefined") return null;
  return (window as unknown as { ezoSensingProvider?: SensingProvider }).ezoSensingProvider ?? null;
}
