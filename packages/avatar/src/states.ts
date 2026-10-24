/** What EZO is doing, and how each state looks. */
export const AVATAR_STATES = ["idle", "listening", "thinking", "speaking", "error"] as const;
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
}

const LOOKS: Record<AvatarState, Look> = {
  idle: { energy: 0.3, warmth: 0.75, listen: 0, think: 0, speak: 0, error: 0 },
  listening: { energy: 0.55, warmth: 0.8, listen: 1, think: 0, speak: 0, error: 0 },
  thinking: { energy: 0.6, warmth: 0.6, listen: 0, think: 1, speak: 0, error: 0 },
  speaking: { energy: 0.75, warmth: 1, listen: 0, think: 0, speak: 1, error: 0 },
  error: { energy: 0.35, warmth: 0.25, listen: 0, think: 0, speak: 0, error: 1 },
};

export function lookFor(state: AvatarState): Look {
  return LOOKS[state];
}

/** Frame-rate independent easing of every parameter towards `target`. */
export function easeLook(current: Look, target: Look, dt: number, rate = 4): Look {
  const k = 1 - Math.exp(-dt * rate);
  return {
    energy: current.energy + (target.energy - current.energy) * k,
    warmth: current.warmth + (target.warmth - current.warmth) * k,
    listen: current.listen + (target.listen - current.listen) * k,
    think: current.think + (target.think - current.think) * k,
    speak: current.speak + (target.speak - current.speak) * k,
    error: current.error + (target.error - current.error) * k,
  };
}

/** Accepts the richer app states (searching, reading, completed…) and maps them to a look. */
export function toAvatarState(state: string): AvatarState {
  switch (state) {
    case "listening":
    case "speaking":
    case "error":
    case "idle":
      return state;
    case "thinking":
    case "searching":
    case "reading":
    case "coding":
    case "creating":
    case "working":
      return "thinking";
    default:
      return "idle";
  }
}
