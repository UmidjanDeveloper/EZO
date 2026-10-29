import { describe, expect, it } from "vitest";
import { AttentionFilter } from "./attention";
import { buildEnergyFigure, ENERGY, facialField } from "./energy-figure";

describe("energy figure", () => {
  it("is deterministic, finite and keeps every light family in adaptive draws", () => {
    const a = buildEnergyFigure("high"), b = buildEnergyFigure("high");
    expect(a.positions).toEqual(b.positions);
    expect(a.count).toBeGreaterThan(40_000);
    expect([...a.positions, ...a.data, ...a.extra].every(Number.isFinite)).toBe(true);
    for (const name of Object.keys(ENERGY) as (keyof typeof ENERGY)[]) {
      const kind = ENERGY[name];
      expect(a.counts[name]).toBeGreaterThan(0);
      // The first 40% still contains every family after deterministic interleaving.
      const prefix = a.data.slice(0, Math.floor(a.count * 0.4) * 4);
      expect(prefix.some((v, i) => i % 4 === 0 && v === kind)).toBe(true);
    }
    expect(buildEnergyFigure("low").count).toBeLessThan(a.count);
  });
  it("keeps amber light inside the face and supports a wave-free head framing", () => {
    expect(facialField(0, 0.6)).toBeGreaterThan(0.9);
    expect(facialField(0.5, 0.6)).toBeLessThan(0.01);
    expect(facialField(0, 1.3)).toBeLessThan(0.01);
    const figure = buildEnergyFigure("low", false);
    expect(figure.counts.wave).toBe(0);
    expect(figure.counts.contour).toBeGreaterThan(0);
  });
});

describe("permission-based attention filter", () => {
  it("calibrates the first pose, smooths movement and expires missing faces", () => {
    const filter = new AttentionFilter();
    expect(filter.update({ yaw: 0.4, pitch: -0.2 }, 0)).toEqual({ yaw: 0, pitch: 0 });
    const moved = filter.update({ yaw: 0.6, pitch: -0.2 }, 0.1)!;
    expect(moved.yaw).toBeGreaterThan(0);
    expect(moved.yaw).toBeLessThan(0.28);
    expect(filter.update(null, 0.2)).toEqual(moved);
    expect(filter.update(null, 1)).toBeNull();
  });
  it("rejects jumps and non-finite samples; reset recalibrates", () => {
    const filter = new AttentionFilter();
    filter.update({ yaw: 0, pitch: 0 }, 0);
    expect(filter.update({ yaw: 1, pitch: 1 }, 0.1)!.yaw).toBe(0);
    expect(filter.update({ yaw: NaN, pitch: 0 }, 0.2)!.yaw).toBe(0);
    filter.reset();
    expect(filter.update({ yaw: 0.7, pitch: 0.3 }, 1)).toEqual({ yaw: 0, pitch: 0 });
  });
});
