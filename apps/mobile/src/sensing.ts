/**
 * Where the camera/gesture sensing engine plugs into the Android app (same shape as the
 * web and Windows slots). The stage consumes frames through @ezo/avatar's AttentionDriver
 * and never opens the camera itself. No provider is bundled in this build, so the control
 * is disabled and says so; a test may install a SIMULATED provider on
 * `window.ezoSensingProvider`, which the stage labels as simulated.
 */
import type { ClapEvent, HandTarget, TrackingFrame, VisionStatus } from "@ezo/avatar";

export interface SensingSession {
  stop(): void;
}

export interface SensingProvider {
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
  return (window as unknown as { ezoSensingProvider?: SensingProvider }).ezoSensingProvider ?? null;
}
