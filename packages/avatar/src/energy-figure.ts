/** Pure light geometry, not a character mesh. Anatomy is sampled into luminous contours. */
import { clamp, createRandom, gaussian, smoothstep } from "./random";
import { bodyWidth, CHIN_Y, faceRelief, headWidth, TOP_Y, BOTTOM_Y, figureWidth } from "./anatomy";

export const ENERGY = { contour: 0, torso: 1, rim: 2, dust: 3, filament: 4, glow: 5, wave: 6, spark: 7 } as const;
export type EnergyPart = keyof typeof ENERGY;
export interface EnergyFigure {
  count: number;
  positions: Float32Array;
  data: Float32Array;
  extra: Float32Array;
  counts: Record<EnergyPart, number>;
  silhouette: Float32Array;
}

class LightBuilder {
  positions: number[] = [];
  data: number[] = [];
  extra: number[] = [];
  counts: Record<EnergyPart, number> = { contour: 0, torso: 0, rim: 0, dust: 0, filament: 0, glow: 0, wave: 0, spark: 0 };
  constructor(readonly random: () => number) {}
  add(part: EnergyPart, x: number, y: number, z: number, brightness: number, warmth: number, a = 0, b = 0) {
    this.positions.push(x, y, z);
    this.data.push(ENERGY[part], this.random(), clamp(brightness, 0, 1), clamp(warmth, 0, 1));
    this.extra.push(a, b);
    this.counts[part]++;
  }
}

function depth(y: number) {
  const t = (y - 0.62) / 0.66;
  return Math.abs(t) >= 1 ? 0 : 0.54 * Math.sqrt(1 - t * t);
}

/** The amber region is a field of horizontal contours, never eyes / lips / skin. */
export function facialField(x: number, y: number, facing = 1) {
  return Math.exp(-Math.pow(x / 0.31, 4) - Math.pow((y - 0.58) / 0.43, 4)) * smoothstep(0.05, 0.65, facing);
}

function shoulderTop(x: number) {
  const ax = Math.abs(x);
  if (ax <= bodyWidth(0.15)) return 0.15;
  let lo = BOTTOM_Y, hi = 0.15;
  for (let i = 0; i < 25; i++) {
    const mid = (lo + hi) / 2;
    if (bodyWidth(mid) >= ax) lo = mid; else hi = mid;
  }
  return lo;
}

export function buildEnergyFigure(quality: "high" | "low", terrain = true, seed = 2026): EnergyFigure {
  const high = quality === "high";
  const r = createRandom(seed);
  const b = new LightBuilder(r);
  // Scan spacing is in anatomical units. Dense lines remain continuous after projection.
  const spacing = high ? 0.014 : 0.024;
  const density = high ? 235 : 140;
  for (let y = TOP_Y - 0.009; y > CHIN_Y + 0.005; y -= spacing) {
    const w = headWidth(y), d = depth(y);
    if (w < 0.012) continue;
    const n = Math.max(12, Math.round((w + d) * density));
    for (let i = 0; i < n; i++) {
      const a = -0.18 * Math.PI + (i + r() * 0.35) / n * Math.PI * 1.36;
      const facing = Math.sin(a);
      const x = w * Math.cos(a);
      const relief = Math.max(0, facing) * faceRelief(x, y);
      const warm = facialField(x, y, facing);
      const nx = Math.cos(a) / w, nz = facing / Math.max(d, 0.001);
      const len = Math.hypot(nx, nz) || 1;
      b.add("contour", x, y + relief * 0.13, d * facing + relief, 0.6 + r() * 0.4, warm, nx / len, nz / len);
    }
  }
  // Neck, trapezius and chest: one continuous family of scans, not a solid torso.
  const bodyStep = high ? 0.009 : 0.017;
  for (let offset = 0.012; offset < 1.95; offset += high ? 0.022 : 0.037) {
    const dip = 0.17 * smoothstep(0.3, 1.5, offset);
    for (let x = -1.47; x < 1.47; x += bodyStep) {
      const px = x + (r() - 0.5) * bodyStep * 0.3;
      const y = shoulderTop(px) - offset - dip * Math.exp(-Math.pow(px / 0.6, 2));
      const w = bodyWidth(y);
      if (y < BOTTOM_Y || Math.abs(px) > w) continue;
      const u = clamp(px / w, -1, 1);
      const z = (y > -0.35 ? 0.85 * w : 0.48) * Math.sqrt(1 - u * u);
      b.add("torso", px, y, z, 0.4 + r() * 0.6, 0, u, Math.sqrt(1 - u * u));
    }
  }
  // Electric silhouette, deliberately broken into fine luminous strands.
  for (let y = BOTTOM_Y; y < TOP_Y; y += high ? 0.004 : 0.008) {
    const w = figureWidth(y);
    for (const side of [-1, 1]) {
      for (let k = 0; k < (high ? 3 : 2); k++) {
        b.add("rim", side * (w + (r() - 0.5) * 0.012), y, (r() - 0.5) * 0.035, 0.55 + r() * 0.45, 0, side, y);
      }
    }
  }
  // Fine neck / shoulder filaments. Each carries its own phase along the strand.
  const paths = high ? 42 : 22;
  for (let path = 0; path < paths; path++) {
    const side = path % 2 ? -1 : 1;
    const spread = r();
    const x0 = side * (0.025 + spread * 0.2), x1 = side * (0.18 + spread * 1.12);
    const y0 = -0.08 - r() * 0.2, y1 = -0.65 - r() * 1.05;
    const n = high ? 85 : 48;
    for (let j = 0; j < n; j++) {
      const t = j / (n - 1);
      const x = x0 + (x1 - x0) * t + Math.sin(t * 8 + path) * 0.024 * Math.sin(t * Math.PI);
      const y = y0 + (y1 - y0) * t;
      b.add("filament", x, y, 0.44 + 0.06 * Math.sin(path), 0.4 + r() * 0.6, path % 7 === 0 ? 0.8 : 0.08, t, path / paths);
    }
  }
  // Soft amber radiance underneath the facial scans.
  for (let i = 0; i < (high ? 460 : 220); i++) {
    const x = gaussian(r) * 0.19, y = 0.58 + gaussian(r) * 0.23;
    if (y < 0.08 || y > 1.15 || Math.abs(x) > headWidth(y) * 0.85) continue;
    const u = x / headWidth(y);
    b.add("glow", x, y, depth(y) * Math.sqrt(1 - u * u) + faceRelief(x, y) + 0.025, 0.35 + r() * 0.65, facialField(x, y));
  }
  // A sparse, deep particle field with slow non-repeating motion in the shader.
  for (let i = 0; i < (high ? 3400 : 1300); i++) {
    const a = r() * Math.PI * 2;
    const radius = 0.65 + Math.pow(r(), 0.6) * 2.6;
    const x = Math.cos(a) * radius, y = 0.3 + Math.sin(a) * radius * 0.65;
    b.add("dust", x, y, -0.6 - r() * 2.5, 0.12 + r() * 0.6, r() < 0.09 ? 0.8 : 0, Math.cos(a), Math.sin(a));
  }
  // Flowing cyan/gold wave ribbons behind the bust; no polygon landscape or terrain.
  if (terrain) {
    const ribbons = high ? 24 : 14, samples = high ? 240 : 150;
    for (let ribbon = 0; ribbon < ribbons; ribbon++) {
      const side = ribbon % 2 ? -1 : 1;
      const lane = Math.floor(ribbon / 2);
      for (let j = 0; j < samples; j++) {
        const t = j / (samples - 1);
        const x = side * (0.65 + t * 3.5);
        const y = -0.9 + Math.sin(t * 5.2 + lane * 0.15) * (0.28 + t * 0.42) + lane * 0.035;
        const z = -1.2 - lane * 0.065;
        const gold = ribbon % 6 === 0;
        b.add("wave", x, y + (r() - 0.5) * 0.012, z, (0.25 + 0.65 * Math.sin(Math.PI * t)) * (gold ? 1 : 0.7), gold ? 0.9 : 0, t, lane / 12);
      }
    }
  }
  for (let i = 0; i < (high ? 220 : 100); i++) {
    const a = r() * Math.PI * 2, rad = Math.abs(gaussian(r)) * 0.075;
    b.add("spark", Math.cos(a) * rad, -1.3 + Math.sin(a) * rad, 0.52, 0.45 + r() * 0.55, 0.45, Math.cos(a), Math.sin(a));
  }
  // Depth-only occluder. It is never shaded or displayed as a surface.
  const silhouette: number[] = [];
  let prev: [number, number] | null = null;
  for (let y = TOP_Y; y >= BOTTOM_Y - 0.02; y -= 0.02) {
    const w = figureWidth(Math.max(y, BOTTOM_Y)) * 0.97;
    if (prev) silhouette.push(-prev[1], prev[0], prev[1], prev[0], -w, y, prev[1], prev[0], w, y, -w, y);
    prev = [y, w];
  }
  // Interleave kinds so adaptive draw-count reduction preserves the whole composition,
  // rather than deleting the last-built wave ribbons. Deterministic, no frame allocations.
  const count = b.positions.length / 3;
  const positions = new Float32Array(b.positions), data = new Float32Array(b.data), extra = new Float32Array(b.extra);
  for (let i = count - 1; i > 0; i--) {
    const j = Math.floor(r() * (i + 1));
    for (let k = 0; k < 3; k++) { const v = positions[i * 3 + k]!; positions[i * 3 + k] = positions[j * 3 + k]!; positions[j * 3 + k] = v; }
    for (let k = 0; k < 4; k++) { const v = data[i * 4 + k]!; data[i * 4 + k] = data[j * 4 + k]!; data[j * 4 + k] = v; }
    for (let k = 0; k < 2; k++) { const v = extra[i * 2 + k]!; extra[i * 2 + k] = extra[j * 2 + k]!; extra[j * 2 + k] = v; }
  }
  return { count, positions, data, extra, counts: b.counts, silhouette: new Float32Array(silhouette) };
}
