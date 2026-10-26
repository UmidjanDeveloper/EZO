/**
 * EZO's visible state: what the user sees EZO doing.
 *
 * One small state machine shared by text chat and voice. The server reports
 * real tool activity ("searching", "reading", …) through the chat stream; the
 * UI never invents a stage it was not told about.
 */

export const EZO_STATES = [
  "idle",
  "listening",
  "recognizing",
  "thinking",
  "speaking",
  "searching",
  "reading",
  "coding",
  "creating",
  "working",
  "completed",
  "error",
  "offline",
] as const;

export type EzoState = (typeof EZO_STATES)[number];

/** Stages the API may send in an `activity` event. Unknown stages show as "working". */
const ACTIVITY_STAGES: ReadonlySet<EzoState> = new Set(["thinking", "searching", "reading", "coding", "creating", "working"]);

export function stageToState(stage: string): EzoState {
  return ACTIVITY_STAGES.has(stage as EzoState) ? (stage as EzoState) : "working";
}

export type EzoEvent =
  | { type: "send" }
  | { type: "activity"; stage: string }
  | { type: "delta" }
  | { type: "done" }
  | { type: "error" }
  | { type: "stopped" }
  | { type: "settle" };

/** Pure transition function; components keep the result in state. */
export function nextEzoState(current: EzoState, event: EzoEvent): EzoState {
  switch (event.type) {
    case "send":
      return "thinking";
    case "activity":
      return current === "completed" || current === "error" ? current : stageToState(event.stage);
    case "delta":
      return current === "completed" || current === "error" ? current : "speaking";
    case "done":
      return "completed";
    case "error":
      return "error";
    case "stopped":
      return current === "completed" || current === "error" ? current : "idle";
    case "settle":
      return current === "completed" || current === "error" ? "idle" : current;
  }
}

export type VoicePhase = "idle" | "listening" | "recognizing" | "thinking" | "speaking";

/** Server stages worth showing while EZO prepares a spoken reply. */
const VOICE_PASS_THROUGH: ReadonlySet<EzoState> = new Set(["searching", "reading", "coding", "creating", "working", "error"]);

/** Combine the voice loop's phase (microphone, speech) with the chat stream's state. */
export function voicePresence(phase: VoicePhase, session: EzoState): EzoState {
  if (phase === "listening" || phase === "recognizing" || phase === "speaking") return phase;
  if (phase === "thinking") return VOICE_PASS_THROUGH.has(session) ? session : "thinking";
  return session === "error" ? "error" : "idle";
}

/** How long a finishing state stays visible before EZO returns to idle. */
export const SETTLE_AFTER_MS: Partial<Record<EzoState, number>> = { completed: 1600, error: 6000 };

export type RobotFace = "idle" | "listening" | "thinking" | "speaking";
export type Tone = "accent" | "accent-2" | "success" | "danger";

export interface PresenceLook {
  /** Expression of the robot face. */
  face: RobotFace;
  /** Colour of the light (eyes, glow, rings). */
  tone: Tone;
  /** Ring rotation period in seconds (lower = busier). */
  spin: number;
  /** True while EZO is busy (drives aria-busy and the header status). */
  busy: boolean;
}

const LOOKS: Record<EzoState, PresenceLook> = {
  idle: { face: "idle", tone: "accent", spin: 48, busy: false },
  listening: { face: "listening", tone: "accent", spin: 30, busy: true },
  recognizing: { face: "listening", tone: "accent-2", spin: 14, busy: true },
  thinking: { face: "thinking", tone: "accent-2", spin: 9, busy: true },
  speaking: { face: "speaking", tone: "accent", spin: 20, busy: true },
  searching: { face: "thinking", tone: "accent-2", spin: 6, busy: true },
  reading: { face: "thinking", tone: "accent", spin: 12, busy: true },
  coding: { face: "thinking", tone: "accent-2", spin: 10, busy: true },
  creating: { face: "thinking", tone: "accent-2", spin: 14, busy: true },
  working: { face: "thinking", tone: "accent-2", spin: 10, busy: true },
  completed: { face: "idle", tone: "success", spin: 36, busy: false },
  error: { face: "idle", tone: "danger", spin: 60, busy: false },
  offline: { face: "idle", tone: "danger", spin: 120, busy: false },
};

export function presenceLook(state: EzoState): PresenceLook {
  return LOOKS[state];
}

export const TONE_VAR: Record<Tone, string> = {
  accent: "var(--accent)",
  "accent-2": "var(--accent-2)",
  success: "var(--success)",
  danger: "var(--danger)",
};
