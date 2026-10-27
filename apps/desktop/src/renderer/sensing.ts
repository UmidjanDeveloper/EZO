/**
 * Where the camera/gesture sensing engine plugs into the Windows app.
 *
 * The engine (packages/face-tracking and the hand/clap work, owned separately) exposes a
 * provider with this shape; the pill consumes it through @ezo/avatar's AttentionDriver and
 * never opens the camera itself. No provider is bundled in this build, so the camera button
 * says so instead of asking for a permission it could not use. A test may install a
 * SIMULATED provider on `window.ezoSensingProvider`; the pill labels it as simulated.
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
  const injected = (window as unknown as { ezoSensingProvider?: SensingProvider }).ezoSensingProvider;
  return injected ?? null;
}
