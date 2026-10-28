/**
 * The figure's geometry: every glowing point of EZO's head, shoulders and the
 * landscape behind them, built once on the CPU. Animation happens in the
 * vertex shader, so this module is pure and unit-tested.
 *
 * Units: the head is about 1.3 tall, y points up, z towards the viewer.
 * Original EZO design (procedural contour lines + particles), see
 * docs/devices/HUMANOID.md.
 */
import { clamp, createRandom, gaussian, smoothstep } from "./random";

export const KIND = {
  head: 0, // contour rings of the head
  body: 1, // neck rings and the arcs over the shoulders and chest
  outline: 2, // the bright silhouette edge
  halo: 3, // spray of particles around the head
  vein: 4, // warm lines rising through the neck
  core: 5, // soft glow sprites in the face: EZO's "voice"
  terrain: 6, // particle mountains behind the figure
  emblem: 7, // the small light on the chest
  eye: 8, // eye outline, iris and pupil (extra = local eye coordinates)
  lid: 9, // upper eyelid line (closes with the blink)
  brow: 10, // eyebrow arcs
  mouth: 11, // lips and the jaw line below them
} as const;
export type KindName = keyof typeof KIND;

export interface FigureOptions {
  quality: "high" | "low";
  /** Mountains behind the figure (off for small views such as the desktop pill). */
  terrain: boolean;
  /** Reference-style contour face, without illustrative eyes/lips. */
  style?: "expressive" | "holographic";
  seed?: number;
}

export interface Figure {
  count: number;
  /** x, y, z per point. */
  positions: Float32Array;
  /** kind, seed (0..1), brightness (0..1), warmth (0..1) per point. */
  data: Float32Array;
  /**
   * Two extra values per point. Head/body/outline: the surface normal (x, z).
   * Halo: drift direction (x, y). Vein: position along the vein (0..1), 0.
   * Eye/lid/brow: local coordinates u (-1..1 across) and v (-1..1 up). Mouth: u, lower (0/1).
   */
  extra: Float32Array;
  counts: Record<KindName, number>;
  /** Filled silhouette (x, y pairs, triangles) used to hide what is behind the figure. */
  silhouette: Float32Array;
}

export const HEAD_CENTER = { x: 0, y: 0.62 } as const;
const HEAD_RX = 0.5;
const HEAD_RY = 0.66;
const HEAD_DEPTH = 0.56;
export const CHIN_Y = -0.04;
export const BOTTOM_Y = -1.8;
export const TOP_Y = 1.28;
const CHEST = { x: 0, y: -1.47 } as const;

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

function headDepth(y: number): number {
  const t = (y - HEAD_CENTER.y) / HEAD_RY;
  return t <= -1 || t >= 1 ? 0 : HEAD_DEPTH * Math.sqrt(1 - t * t);
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

/** Depth of the front surface of the neck/torso. */
function bodyFront(x: number, y: number): number {
  const w = bodyWidth(y);
  if (w <= 0) return 0;
  const u = clamp(x / w, -1, 1);
  return (y > -0.35 ? 0.85 * w : 0.48) * Math.sqrt(1 - u * u);
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

/** How strongly a point of the face carries EZO's warm "voice" light (0..1). */
export function faceWarmth(x: number, y: number, facing: number): number {
  return Math.exp(-((x / 0.3) ** 2 + ((y - 0.47) / 0.28) ** 2)) * smoothstep(0, 0.5, facing);
}

// --- value noise for the mountains -----------------------------------------------------------

function hash(x: number, y: number, seed: number): number {
  const s = Math.sin(x * 127.1 + y * 311.7 + seed * 74.7) * 43758.5453;
  return s - Math.floor(s);
}

function valueNoise(x: number, y: number, seed: number): number {
  const xi = Math.floor(x);
  const yi = Math.floor(y);
  const fx = x - xi;
  const fy = y - yi;
  const ux = fx * fx * (3 - 2 * fx);
  const uy = fy * fy * (3 - 2 * fy);
  const a = hash(xi, yi, seed);
  const b = hash(xi + 1, yi, seed);
  const c = hash(xi, yi + 1, seed);
  const d = hash(xi + 1, yi + 1, seed);
  return a + (b - a) * ux + (c - a) * uy + (a - b - c + d) * ux * uy;
}

/** Ridged multi-octave noise in 0..1: sharp mountain crests. */
export function ridges(x: number, y: number, seed: number): number {
  let sum = 0;
  let amp = 0.5;
  let freq = 1;
  let norm = 0;
  for (let octave = 0; octave < 4; octave++) {
    const n = 1 - Math.abs(2 * valueNoise(x * freq, y * freq, seed + octave) - 1);
    sum += amp * n * n;
    norm += amp;
    amp *= 0.5;
    freq *= 2.1;
  }
  return sum / norm;
}

// --- builder ---------------------------------------------------------------------------------

class Builder {
  positions: number[] = [];
  data: number[] = [];
  extra: number[] = [];
  counts: Record<KindName, number> = { head: 0, body: 0, outline: 0, halo: 0, vein: 0, core: 0, terrain: 0, emblem: 0, eye: 0, lid: 0, brow: 0, mouth: 0 };

  constructor(readonly random: () => number) {}

  push(kind: KindName, x: number, y: number, z: number, bright: number, warm: number, e0 = 0, e1 = 0): void {
    this.positions.push(x, y, z);
    this.data.push(KIND[kind], this.random(), clamp(bright, 0, 1), clamp(warm, 0, 1));
    this.extra.push(e0, e1);
    this.counts[kind] += 1;
  }
}

const FRONT_START = -0.22 * Math.PI; // rings cover the front and a little of the sides
const FRONT_END = 1.22 * Math.PI;

function addHead(b: Builder, spacing: number, density: number): void {
  const r = b.random;
  for (let y = TOP_Y - spacing * 0.6; y > CHIN_Y + 0.01; y -= spacing) {
    const w = headWidth(y);
    const d = headDepth(y);
    if (w < 0.02) continue;
    const arc = (FRONT_END - FRONT_START) * 0.5 * (w + d);
    const n = Math.max(8, Math.round(arc * density));
    for (let i = 0; i < n; i++) {
      const theta = FRONT_START + ((i + r() * 0.6) / n) * (FRONT_END - FRONT_START);
      const facing = Math.sin(theta);
      const x = w * Math.cos(theta) + (r() - 0.5) * 0.004;
      const relief = facing > 0 ? faceRelief(x, y) * facing : 0;
      const z = d * facing + relief;
      let nx = Math.cos(theta) / w;
      let nz = facing / Math.max(d, 1e-3);
      const len = Math.hypot(nx, nz) || 1;
      nx /= len;
      nz /= len;
      // Contours bend over the relief (brow, nose, lips) like lines projected onto a real face.
      const bend = relief * 0.25;
      b.push("head", x, y + bend + (r() - 0.5) * 0.003, z, 0.7 + 0.3 * r(), faceWarmth(x, y, facing), nx, nz);
    }
  }
}

/** Highest point of the neck/shoulder outline above x (the neck top under the head). */
function shoulderTop(x: number): number {
  const ax = Math.abs(x);
  if (ax <= bodyWidth(0.15)) return 0.15;
  let lo = BOTTOM_Y;
  let hi = 0.15;
  for (let i = 0; i < 30; i++) {
    const mid = (lo + hi) / 2;
    if (bodyWidth(mid) >= ax) lo = mid;
    else hi = mid;
  }
  return lo;
}

/**
 * Neck, shoulders and chest as one family of contour lines that follow the outline:
 * level under the jaw, sloping with the trapezius over the shoulders, and dipping a
 * little towards the sternum lower down.
 */
function addBodyContours(b: Builder, spacing: number, step: number): void {
  const r = b.random;
  const width = bodyWidth(BOTTOM_Y);
  for (let depth = spacing * 0.5; depth < 0.15 - BOTTOM_Y; depth += spacing) {
    const dip = 0.2 * smoothstep(0.35, 1.6, depth);
    for (let x0 = -width; x0 <= width; x0 += step) {
      const x = x0 + (r() - 0.5) * step * 0.5;
      const y = shoulderTop(x) - depth - dip * Math.exp(-((x / 0.6) ** 2)) + (r() - 0.5) * 0.003;
      const w = bodyWidth(y);
      if (y < BOTTOM_Y || Math.abs(x) > w - 0.01) continue;
      if (Math.abs(x) < headWidth(y) + 0.012) continue; // hidden behind the jaw
      const u = x / w;
      const sternum = Math.exp(-(((x / 0.35) ** 2) + ((y - CHEST.y) / 0.5) ** 2));
      b.push("body", x, y, bodyFront(x, y), 0.65 + 0.25 * r() + 0.25 * sternum, 0, u, Math.sqrt(Math.max(0, 1 - u * u)));
    }
  }
}

function addOutline(b: Builder, step: number): void {
  const r = b.random;
  for (let y = TOP_Y; y > BOTTOM_Y; y -= step) {
    const head = headWidth(y);
    const body = bodyWidth(y);
    const w = Math.max(head, body);
    if (w < 0.01) continue;
    for (const side of [-1, 1]) {
      const jitter = (r() - 0.5) * 0.006;
      b.push("outline", side * (w + jitter), y, 0.02, 0.75 + 0.25 * r(), 0, side, 0);
    }
  }
  // The crown: the head outline is nearly horizontal at the top, so sample it by angle too.
  for (let i = 0; i < 160; i++) {
    const x = -0.36 + 0.72 * (i / 159);
    let y = TOP_Y;
    while (headWidth(y) < Math.abs(x) && y > HEAD_CENTER.y) y -= 0.002;
    b.push("outline", x, y, 0.02, 0.8 + 0.2 * r(), 0, x / 0.5, 0);
  }
}

function addHalo(b: Builder, count: number): void {
  const r = b.random;
  for (let i = 0; i < count; i++) {
    if (i < count * 0.82) {
      // Around the head, densest over the crown like hair made of light.
      const a = Math.PI / 2 + gaussian(r) * (r() < 0.7 ? 0.7 : 1.5);
      const out = 1.0 + Math.abs(gaussian(r)) * 0.05 + (r() < 0.3 ? r() * 0.22 : 0);
      const x = HEAD_RX * Math.cos(a) * out;
      const y = HEAD_CENTER.y + HEAD_RY * Math.sin(a) * out;
      const dx = Math.cos(a) * 0.6;
      const dy = Math.sin(a) + 0.35;
      const len = Math.hypot(dx, dy) || 1;
      b.push("halo", x, y, (r() - 0.35) * 0.3, 0.35 + 0.65 * r(), 0, dx / len, dy / len);
    } else {
      // A few sparks rising off the shoulders.
      const x = (0.35 + r() * 0.9) * (r() < 0.5 ? -1 : 1);
      let y = -0.4;
      while (Math.abs(x) > bodyWidth(y) && y > BOTTOM_Y) y -= 0.02;
      b.push("halo", x, y + r() * 0.06, 0.05, 0.2 + 0.4 * r(), 0, x > 0 ? 0.3 : -0.3, 1);
    }
  }
}

function addVeins(b: Builder, step: number): void {
  const r = b.random;
  const paths: [number, number, number, number][] = [
    // start x, start y, end x, end y
    [-0.03, -1.4, -0.08, -0.02],
    [0.02, -1.4, 0.07, -0.04],
    [0, -1.42, -0.01, 0.0],
    [-0.04, -1.38, -0.5, -0.6],
    [0.04, -1.38, 0.52, -0.62],
    [-0.02, -1.0, -0.16, -0.2],
    [0.02, -1.05, 0.17, -0.18],
  ];
  for (const [x0, y0, x1, y1] of paths) {
    const length = Math.hypot(x1 - x0, y1 - y0);
    const n = Math.max(20, Math.round(length / step));
    let wander = 0;
    for (let i = 0; i <= n; i++) {
      const s = i / n;
      wander += (r() - 0.5) * 0.012;
      wander *= 0.96;
      const x = x0 + (x1 - x0) * s + wander + Math.sin(s * 9 + x0 * 40) * 0.012;
      const y = y0 + (y1 - y0) * s;
      b.push("vein", x, y, bodyFront(x, y) + 0.012, 0.6 + 0.4 * r(), 1, s, 0);
    }
  }
}

function addCore(b: Builder, count: number): void {
  const r = b.random;
  for (let i = 0; i < count; i++) {
    const x = gaussian(r) * 0.11;
    const y = 0.54 + gaussian(r) * 0.13; // between the eyes and the lips, leaving the mouth readable
    const w = headWidth(y);
    if (Math.abs(x) > w * 0.8) continue;
    const u = x / Math.max(w, 1e-3);
    const z = headDepth(y) * Math.sqrt(Math.max(0, 1 - u * u)) + faceRelief(x, y) + 0.02;
    const centre = Math.exp(-((x / 0.11) ** 2 + ((y - 0.54) / 0.13) ** 2));
    b.push("core", x, y, z, 0.4 + 0.6 * r(), centre);
  }
}

function addEmblem(b: Builder): void {
  // A small cluster of bright sparks where the veins meet, low on the sternum.
  const r = b.random;
  const z = bodyFront(CHEST.x, CHEST.y) + 0.02;
  for (let i = 0; i < 160; i++) {
    const a = r() * Math.PI * 2;
    const d = Math.abs(gaussian(r)) * 0.045;
    b.push("emblem", CHEST.x + Math.cos(a) * d, CHEST.y + 0.03 + Math.sin(a) * d * 1.3, z, 0.6 + 0.4 * r(), d < 0.02 ? 0.4 : 0, Math.cos(a), Math.sin(a));
  }
}

/** Depth of the front of the face at (x, y): the head surface plus its relief. */
export function faceZ(x: number, y: number): number {
  const w = headWidth(y);
  if (w <= 0) return 0;
  const u = clamp(x / w, -1, 1);
  const facing = Math.sqrt(Math.max(0, 1 - u * u));
  return headDepth(y) * facing + faceRelief(x, y) * facing;
}

/** Eye centres and size, shared with the shader's gaze offsets (face units). */
export const EYE = { x: 0.17, y: 0.675, rx: 0.082, ry: 0.046, iris: 0.034, pupil: 0.016 } as const;
export const MOUTH = { y: 0.33, halfWidth: 0.15 } as const;

/** Almond eye outline: fuller upper lid, flatter lower lid. */
export function eyeOutline(u: number, upper: boolean): number {
  const arc = Math.sqrt(Math.max(0, 1 - u * u));
  return upper ? arc : -0.62 * arc;
}

/**
 * Explicit facial features drawn over the contour rings: eyes with iris and pupil, upper
 * lids, brows and lips. Each point carries local coordinates so the shader can move the
 * iris with the gaze, close the lids, raise the brows and open the jaw with the voice.
 */
function addFeatures(b: Builder, density: number): void {
  const r = b.random;
  const lift = 0.018; // features sit just in front of the surface
  for (const side of [-1, 1]) {
    const cx = side * EYE.x;
    // Eye outline (upper and lower), brightness 0 → outline, warm channel tags the part.
    const n = Math.round(48 * density);
    for (let i = 0; i < n; i++) {
      const u = -1 + (2 * (i + r() * 0.5)) / n;
      for (const upper of [true, false]) {
        const v = eyeOutline(u, upper);
        const x = cx + u * EYE.rx;
        const y = EYE.y + v * EYE.ry;
        b.push("eye", x, y, faceZ(x, y) + lift, 0.75 + 0.25 * r(), 0, u, v);
      }
    }
    // Iris ring + fill, pupil fill. warm = 0.5 iris, 1 pupil.
    const irisRing = Math.round(40 * density);
    for (let i = 0; i < irisRing; i++) {
      const a = ((i + r() * 0.5) / irisRing) * Math.PI * 2;
      const u = (Math.cos(a) * EYE.iris) / EYE.rx;
      const v = (Math.sin(a) * EYE.iris) / EYE.ry;
      const x = cx + u * EYE.rx;
      const y = EYE.y + v * EYE.ry;
      b.push("eye", x, y, faceZ(x, y) + lift, 0.85 + 0.15 * r(), 0.5, u, v);
    }
    const irisFill = Math.round(90 * density);
    for (let i = 0; i < irisFill; i++) {
      const a = r() * Math.PI * 2;
      const rad = EYE.pupil + (EYE.iris - EYE.pupil) * Math.sqrt(r());
      const u = (Math.cos(a) * rad) / EYE.rx;
      const v = (Math.sin(a) * rad) / EYE.ry;
      const x = cx + u * EYE.rx;
      const y = EYE.y + v * EYE.ry;
      b.push("eye", x, y, faceZ(x, y) + lift, 0.35 + 0.45 * r(), 0.5, u, v);
    }
    const pupil = Math.round(50 * density);
    for (let i = 0; i < pupil; i++) {
      const a = r() * Math.PI * 2;
      const rad = EYE.pupil * Math.sqrt(r());
      const u = (Math.cos(a) * rad) / EYE.rx;
      const v = (Math.sin(a) * rad) / EYE.ry;
      const x = cx + u * EYE.rx;
      const y = EYE.y + v * EYE.ry;
      b.push("eye", x, y, faceZ(x, y) + lift, 0.9, 1, u, v);
    }
    // Upper lid: a second, slightly higher arc that comes down over the eye when blinking.
    const lid = Math.round(44 * density);
    for (let i = 0; i < lid; i++) {
      const u = -1.05 + (2.1 * (i + r() * 0.5)) / lid;
      const v = eyeOutline(clamp(u, -1, 1), true) * 1.12 + 0.08;
      const x = cx + u * EYE.rx;
      const y = EYE.y + v * EYE.ry;
      b.push("lid", x, y, faceZ(x, y) + lift * 1.2, 0.7 + 0.3 * r(), 0, u, v);
    }
    // Brow: an arch from the inner corner outwards, thicker in the middle.
    const brow = Math.round(60 * density);
    for (let i = 0; i < brow; i++) {
      const u = -1 + (2 * (i + r() * 0.5)) / brow; // -1 inner … 1 outer
      const x = side * (0.045 + 0.125 * (u + 1)); // |x| 0.045 (inner) … 0.295 (outer)
      const arch = 0.76 + 0.045 * Math.sin(((u + 1) / 2) * Math.PI) - 0.01 * u;
      const y = arch + (r() - 0.5) * 0.008;
      b.push("brow", x, y, faceZ(x, y) + lift, 0.6 + 0.4 * r(), 0, u, 0);
    }
  }
  // Lips: upper and lower lines; the lower line and the jaw move with the voice.
  const lips = Math.round(80 * density);
  for (let i = 0; i < lips; i++) {
    const u = -1 + (2 * (i + r() * 0.5)) / lips;
    const x = u * MOUTH.halfWidth;
    const bow = 0.012 * Math.cos(u * Math.PI * 1.5) * (1 - u * u); // cupid's bow hint
    const yUpper = MOUTH.y + 0.006 + bow * 0.5;
    const yLower = MOUTH.y - 0.012 - 0.01 * (1 - u * u);
    b.push("mouth", x, yUpper, faceZ(x, yUpper) + lift, 0.65 + 0.35 * r(), 0, u, 0);
    b.push("mouth", x, yLower, faceZ(x, yLower) + lift, 0.65 + 0.35 * r(), 0, u, 1);
  }
}

function addTerrain(b: Builder, step: number, fill: number, seed: number): void {
  const r = b.random;
  // Ridge lines at increasing distance: bright crests with dust below them.
  for (let layer = 0; layer < 5; layer++) {
    const z = -2.6 - layer * 1.5;
    const base = -1.2 + layer * 0.14;
    const amp = 1.0 + layer * 0.3;
    const dx = step * (1 + layer * 0.45);
    for (let x = -4 - layer * 1.6; x <= 4 + layer * 1.6; x += dx) {
      const px = x + (r() - 0.5) * dx;
      const sides = 0.2 + 0.8 * smoothstep(0.7, 2.6 + layer * 0.6, Math.abs(px)); // low behind the figure
      const ridge = ridges(px * 0.42 + layer * 3.1, layer * 7.3, seed);
      const crestY = base + amp * smoothstep(0.12, 0.62, ridge) * sides * 1.15;
      const lava = r() < 0.12 * sides ? 1 : 0;
      b.push("terrain", px, crestY, z, 0.55 + 0.45 * sides, lava);
      for (let k = 0; k < fill; k++) {
        const drop = Math.abs(gaussian(r)) * 0.35 * (0.4 + sides);
        const glint = r() < 0.02 ? 1 : 0; // occasional warm spark on the slopes
        b.push("terrain", px + (r() - 0.5) * dx * 3, crestY - drop, z + (r() - 0.5) * 0.4, Math.max(0.08, 0.5 - drop) * sides, glint);
      }
    }
  }
}

/** Filled figure outline (triangles), slightly inside the bright edge. */
function silhouette(step: number): Float32Array {
  const out: number[] = [];
  let prev: [number, number] | null = null;
  for (let y = TOP_Y; y >= BOTTOM_Y - step; y -= step) {
    const w = figureWidth(Math.max(y, BOTTOM_Y)) * 0.985;
    if (prev) {
      const [py, pw] = prev;
      out.push(-pw, py, pw, py, -w, y, pw, py, w, y, -w, y);
    }
    prev = [y, w];
  }
  return new Float32Array(out);
}

export function buildFigure(options: FigureOptions): Figure {
  const high = options.quality === "high";
  const seed = options.seed ?? 2026;
  const b = new Builder(createRandom(seed));
  addHead(b, high ? 0.026 : 0.034, high ? 175 : 112);
  addBodyContours(b, high ? 0.034 : 0.05, high ? 0.011 : 0.02);
  addOutline(b, high ? 0.006 : 0.011);
  addHalo(b, high ? 6800 : 1500);
  addVeins(b, high ? 0.006 : 0.01);
  addCore(b, high ? 900 : 420);
  addEmblem(b);
  if (options.style !== "holographic") addFeatures(b, high ? 1 : 0.6);
  if (options.terrain) addTerrain(b, high ? 0.016 : 0.028, high ? 3 : 2, seed);
  return {
    count: Object.values(b.counts).reduce((sum, n) => sum + n, 0),
    positions: new Float32Array(b.positions),
    data: new Float32Array(b.data),
    extra: new Float32Array(b.extra),
    counts: b.counts,
    silhouette: silhouette(0.02),
  };
}
