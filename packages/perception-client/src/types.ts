/** Monotonic performance.now() milliseconds. */
export interface ClapDetected {
  type: "clap_detected";
  timestampMs: number;
  confidence: number;
  /** Heuristic acoustic evidence, not a calibrated probability or command authorization. */
  evidence: "acoustic_transient";
  authorization: "acknowledgement_only";
}
export type Language = "uz" | "en" | "ru";
export type PlaybackEvent =
  | { type: "start"; timestampMs: number }
  | { type: "level"; level: number; timestampMs: number }
  | { type: "end" | "unavailable" | "error"; timestampMs: number };
