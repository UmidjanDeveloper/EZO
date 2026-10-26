/** What EZO is doing, and how each state looks. */
export const AVATAR_STATES = [
  "idle",
  "listening",
  "recognizing",
  "thinking",
  "working",
  "speaking",
  "success",
  "error",
  "offline",
] as const;
export type AvatarState = (typeof AVATAR_STATES)[number];

/** Shader parameters a state moves towards; the avatar eases between them. */
export interface Look {
  /** Overall liveliness: halo drift, breathing, sparkle. */
  energy: number;
  /** Strength of the warm voice light in the face. */
  warmth: number;
  /** Halo drawn in towards the head while EZO listens. */
  listen: number;
  /** Scanning wave and swirl while EZO thinks. */
  think: number;
  /** Face lines ripple with the voice. */
  speak: number;
  /** Red tint after a failure. */
  error: number;
  /** A tool or device is doing real work: fast pulses up the veins, bright chest light. */
  work: number;
  /** A gold flash outwards when something finished well. */
  success: number;
  /** No server or no AI: the figure goes grey and still. */
  offline: number;
}

const LOOKS: Record<AvatarState, Look> = {
  idle: { energy: 0.3, warmth: 0.75, listen: 0, think: 0, speak: 0, error: 0, work: 0, success: 0, offline: 0 },
  listening: { energy: 0.55, warmth: 0.8, listen: 1, think: 0, speak: 0, error: 0, work: 0, success: 0, offline: 0 },
  // Heard, now turning speech into words: the halo is still drawn in, a first scan starts.
  recognizing: { energy: 0.6, warmth: 0.7, listen: 0.6, think: 0.5, speak: 0, error: 0, work: 0, success: 0, offline: 0 },
  thinking: { energy: 0.6, warmth: 0.6, listen: 0, think: 1, speak: 0, error: 0, work: 0, success: 0, offline: 0 },
  working: { energy: 0.85, warmth: 0.7, listen: 0, think: 0.6, speak: 0, error: 0, work: 1, success: 0, offline: 0 },
  speaking: { energy: 0.75, warmth: 1, listen: 0, think: 0, speak: 1, error: 0, work: 0, success: 0, offline: 0 },
  success: { energy: 0.9, warmth: 0.95, listen: 0, think: 0, speak: 0, error: 0, work: 0, success: 1, offline: 0 },
  error: { energy: 0.35, warmth: 0.25, listen: 0, think: 0, speak: 0, error: 1, work: 0, success: 0, offline: 0 },
  offline: { energy: 0.12, warmth: 0.1, listen: 0, think: 0, speak: 0, error: 0, work: 0, success: 0, offline: 1 },
};

export function lookFor(state: AvatarState): Look {
  return LOOKS[state];
}

/** Frame-rate independent easing of every parameter towards `target`. */
export function easeLook(current: Look, target: Look, dt: number, rate = 4): Look {
  const k = 1 - Math.exp(-dt * rate);
  const out = { ...current };
  for (const key of Object.keys(out) as (keyof Look)[]) out[key] = current[key] + (target[key] - current[key]) * k;
  return out;
}

/** States that are a moment, not a condition: the avatar returns to idle by itself. */
export const TRANSIENT_STATES: Partial<Record<AvatarState, number>> = { success: 1.6 };

/** Accepts the richer app states (searching, reading, completed…) and maps them to a look. */
export function toAvatarState(state: string): AvatarState {
  switch (state) {
    case "listening":
    case "recognizing":
    case "speaking":
    case "error":
    case "idle":
    case "working":
    case "success":
    case "offline":
      return state;
    case "transcribing":
      return "recognizing";
    case "thinking":
      return "thinking";
    // Real tool activity the server reported: the figure visibly works, not just thinks.
    case "searching":
    case "reading":
    case "coding":
    case "creating":
    case "acting":
    case "executing":
    case "tool":
    case "running":
      return "working";
    case "completed":
    case "done":
      return "success";
    case "disconnected":
    case "unavailable":
      return "offline";
    default:
      return "idle";
  }
}
