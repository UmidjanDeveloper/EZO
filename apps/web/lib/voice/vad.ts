/**
 * A tiny voice-activity detector: decides when the user started speaking and
 * when they stopped (a pause after speech). Pure, so it is unit-tested.
 */

export interface VadConfig {
  /** RMS level (0..1) that counts as speech. */
  threshold: number;
  /** Silence after speech that ends the utterance. */
  endSilenceMs: number;
  /** Give up if nothing is said for this long. */
  noSpeechMs: number;
  /** Hard limit for one utterance. */
  maxMs: number;
}

export const DEFAULT_VAD: VadConfig = { threshold: 0.02, endSilenceMs: 1200, noSpeechMs: 8000, maxMs: 45_000 };

export interface VadState {
  startedAt: number;
  speechAt: number | null;
  lastLoudAt: number | null;
}

export type VadAction = "continue" | "end" | "no-speech";

export function vadStart(now: number): VadState {
  return { startedAt: now, speechAt: null, lastLoudAt: null };
}

export function vadStep(state: VadState, rms: number, now: number, config: VadConfig = DEFAULT_VAD): [VadState, VadAction] {
  const loud = rms >= config.threshold;
  const next: VadState = loud
    ? { ...state, speechAt: state.speechAt ?? now, lastLoudAt: now }
    : state;
  if (now - next.startedAt >= config.maxMs) return [next, next.speechAt === null ? "no-speech" : "end"];
  if (next.speechAt === null) return [next, now - next.startedAt >= config.noSpeechMs ? "no-speech" : "continue"];
  if (!loud && next.lastLoudAt !== null && now - next.lastLoudAt >= config.endSilenceMs) return [next, "end"];
  return [next, "continue"];
}

export function rmsOf(samples: Float32Array): number {
  let sum = 0;
  for (const sample of samples) sum += sample * sample;
  return samples.length ? Math.sqrt(sum / samples.length) : 0;
}

/** Measured speaking time of an utterance (first speech to last loud moment), in seconds. */
export function speakingSeconds(state: VadState): number | null {
  if (state.speechAt === null || state.lastLoudAt === null) return null;
  return Math.round((state.lastLoudAt - state.speechAt) / 100) / 10;
}
