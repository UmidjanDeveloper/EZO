/**
 * Shared anatomical measurements for the energy composition. These are contour
 * guides, not a surface mesh: the renderer emits light scans/filaments only.
 * Units: head ~1.3 tall, y up, z toward the viewer. Original EZO design.
 */
import { clamp, smoothstep } from "./random";

export const CHIN_Y = -0.04;
export const BOTTOM_Y = -1.8;
export const TOP_Y = 1.28;

// Head outline: half-width by height (crown, temples, cheekbones, jaw, chin).
const HEAD_KNOTS: readonly [number, number][] = [
  [1.28, 0],
  [1.25, 0.17],
  [1.18, 0.3],
  [1.05, 0.42],
  [0.9, 0.48],
  [0.72, 0.5],
  [0.55, 0.49],
  [0.38, 0.45],
  [0.22, 0.42],
  [0.1, 0.34],
  [0.02, 0.19],
  [-0.025, 0.07],
  [-0.04, 0],
];

function interpolate(knots: readonly [number, number][], y: number): number {
  if (y > knots[0]![0]) return 0;
  for (let i = 1; i < knots.length; i++) {
    const [y1, w1] = knots[i]!;
    const [y0, w0] = knots[i - 1]!;
    if (y >= y1) return w0 + (w1 - w0) * smoothstep(y0, y1, y);
  }
  return knots[knots.length - 1]![1];
}

/** Half-width of the head at height y (0 outside the head). */
export function headWidth(y: number): number {
  return y < CHIN_Y ? 0 : interpolate(HEAD_KNOTS, y);
}

// Neck and shoulders: half-width by height, smoothly interpolated between knots.
// A strong neck that flows into sloping trapezius lines and broad shoulders (no "stand").
const BODY_KNOTS: readonly [number, number][] = [
  [0.15, 0.33],
  [-0.08, 0.34],
  [-0.22, 0.4],
  [-0.34, 0.56],
  [-0.48, 0.84],
  [-0.64, 1.1],
  [-0.84, 1.3],
  [-1.1, 1.4],
  [-1.8, 1.47],
];

/** Half-width of the neck/torso at height y (0 above the neck). */
export function bodyWidth(y: number): number {
  return interpolate(BODY_KNOTS, y);
}

/** Visible half-width of the whole figure at height y. */
export function figureWidth(y: number): number {
  return Math.max(headWidth(y), bodyWidth(y));
}

/** Face relief, pushed out along the front of the head. */
export function faceRelief(x: number, y: number): number {
  const g = (dx: number, sx: number, dy: number, sy: number) => Math.exp(-((dx / sx) ** 2 + (dy / sy) ** 2));
  const nose = 0.1 * g(x, 0.06, y - 0.52, 0.12);
  const brow = 0.035 * Math.exp(-(((y - 0.74) / 0.04) ** 2)) * Math.exp(-((x / 0.3) ** 2));
  const eyes = -0.04 * g(Math.abs(x) - 0.17, 0.08, y - 0.67, 0.05);
  const lips = 0.025 * g(x, 0.12, y - 0.33, 0.04);
  const chin = 0.03 * g(x, 0.12, y - 0.12, 0.07);
  return nose + brow + eyes + lips + chin;
}
