/**
 * The face: what EZO's eyes, lids, brows and mouth do, as pure functions of time, state and
 * the live voice level. The geometry lives in figure.ts (addFeatures), the deformation in
 * the vertex shader; this module decides the amounts, so it is unit-tested without a GPU.
 */
import type { Look } from "./states";
import type { Gaze } from "./avatar";

/** Per-frame facial amounts handed to the shader (all 0..1 unless noted). */
export interface FaceAmounts {
  /** 1 = eyes shut. */
  blink: number;
  /** Lids half lowered (offline / exhausted look). */
  droop: number;
  /** Where the irises point, normalised -1..1 (eyes lead the head). */
  eye: Gaze;
  /** Brow height: positive raised (attentive), negative lowered (concentrating). -1..1. */
  brow: number;
  /** Jaw/mouth opening driven by the spoken level. */
  mouth: number;
  /** Mouth corners up (success) or down (error). -1..1. */
  smile: number;
}

export const CLOSED_FACE: FaceAmounts = { blink: 0, droop: 0, eye: { yaw: 0, pitch: 0 }, brow: 0, mouth: 0, smile: 0 };

/** Blink timing: fast close, brief hold, slower open (about 0.24 s in all). */
export const BLINK_CLOSE = 0.07;
export const BLINK_HOLD = 0.04;
export const BLINK_OPEN = 0.13;
export const BLINK_LENGTH = BLINK_CLOSE + BLINK_HOLD + BLINK_OPEN;

/** Lid closure 0..1 at `t` seconds into a blink (0 outside the blink). */
export function blinkCurve(t: number): number {
  if (t < 0 || t >= BLINK_LENGTH) return 0;
  if (t < BLINK_CLOSE) return smooth(t / BLINK_CLOSE);
  if (t < BLINK_CLOSE + BLINK_HOLD) return 1;
  return 1 - smooth((t - BLINK_CLOSE - BLINK_HOLD) / BLINK_OPEN);
}

/** Seconds until the next blink: people blink every 2–6 s, more often when attentive. */
export function nextBlinkDelay(random: number, attentive: number): number {
  const base = 2.2 + 3.8 * random;
  return base * (1 - 0.35 * attentive);
}

/**
 * Where the eyes look: the tracked gaze when there is one (eyes lead the head and go a
 * little further), otherwise a small wander, lifted up-and-aside while thinking.
 */
export function eyeTarget(look: Look, gaze: Gaze | null, time: number): Gaze {
  if (gaze) return { yaw: clamp1(gaze.yaw * 1.25), pitch: clamp1(gaze.pitch * 1.25) };
  const think = look.think;
  const wander = { yaw: 0.18 * Math.sin(time * 0.37) + 0.08 * Math.sin(time * 1.3), pitch: 0.08 * Math.sin(time * 0.53) };
  return {
    yaw: clamp1(wander.yaw * (1 - think) + think * (0.45 + 0.1 * Math.sin(time * 0.8))),
    pitch: clamp1(wander.pitch * (1 - think) + think * 0.55),
  };
}

/** Brows rise with attention (listening) and lower with concentration (thinking, working). */
export function browFor(look: Look): number {
  return clamp1(0.5 * look.listen + 0.25 * look.success - 0.45 * look.think - 0.2 * look.work - 0.35 * look.error);
}

/** Jaw opening from the spoken level: nothing while silent, visible but never gaping. */
export function mouthFor(level: number, look: Look): number {
  const open = Math.max(0, level - 0.04) * 1.15;
  return Math.min(1, open) * look.speak;
}

export function smileFor(look: Look): number {
  return clamp1(0.8 * look.success + 0.15 * look.speak - 0.6 * look.error - 0.4 * look.offline);
}

/** Lids drift half shut when EZO is offline; wide open while listening. */
export function droopFor(look: Look): number {
  return clamp1(0.55 * look.offline - 0.15 * look.listen);
}

function smooth(x: number): number {
  const t = Math.min(1, Math.max(0, x));
  return t * t * (3 - 2 * t);
}

function clamp1(v: number): number {
  return Math.min(1, Math.max(-1, Number.isFinite(v) ? v : 0));
}
