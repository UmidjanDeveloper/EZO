import { describe, expect, it } from "vitest";
import { BOTTOM_Y, buildFigure, CHIN_Y, figureWidth, headWidth, KIND, ridges, TOP_Y } from "./figure";

describe("buildFigure", () => {
  const high = buildFigure({ quality: "high", terrain: true });
  const low = buildFigure({ quality: "low", terrain: false });

  it("has every part of the figure and consistent buffers", () => {
    for (const figure of [high, low]) {
      expect(figure.positions.length).toBe(figure.count * 3);
      expect(figure.data.length).toBe(figure.count * 4);
      expect(figure.extra.length).toBe(figure.count * 2);
      for (const [kind, n] of Object.entries(figure.counts)) {
        if (kind === "terrain" && figure === low) expect(n).toBe(0);
        else expect(n, kind).toBeGreaterThan(30);
      }
    }
  });

  it("stays within a budget phones can draw every frame", () => {
    expect(high.count).toBeLessThan(60_000);
    expect(low.count).toBeLessThan(high.count / 2);
    expect(low.count).toBeLessThan(20_000);
  });

  it("is deterministic and finite", () => {
    const again = buildFigure({ quality: "high", terrain: true });
    expect(again.positions).toEqual(high.positions);
    expect(high.positions.every(Number.isFinite)).toBe(true);
    expect(high.data.every(Number.isFinite)).toBe(true);
    expect(high.extra.every(Number.isFinite)).toBe(true);
  });

  it("keeps the figure's points inside its own silhouette", () => {
    for (let i = 0; i < high.count; i++) {
      const kind = high.data[i * 4]!;
      if (kind !== KIND.head && kind !== KIND.body) continue;
      const x = high.positions[i * 3]!;
      const y = high.positions[i * 3 + 1]!;
      expect(y).toBeLessThanOrEqual(TOP_Y + 0.01);
      expect(y).toBeGreaterThanOrEqual(BOTTOM_Y - 0.01);
      const room = Math.max(figureWidth(y - 0.005), figureWidth(y), figureWidth(y + 0.005));
      expect(Math.abs(x)).toBeLessThanOrEqual(room + 0.01);
    }
  });

  it("puts the warm voice light in the face only", () => {
    let warmFace = 0;
    for (let i = 0; i < high.count; i++) {
      if (high.data[i * 4] !== KIND.head || high.data[i * 4 + 3]! < 0.5) continue;
      warmFace += 1;
      expect(high.positions[i * 3 + 1]!).toBeGreaterThan(0.15); // above the chin
      expect(high.positions[i * 3 + 2]!).toBeGreaterThan(0); // on the front of the head
    }
    expect(warmFace).toBeGreaterThan(200);
  });

  it("has a head shape: widest near the temples, narrow at the chin", () => {
    expect(headWidth(0.7)).toBeGreaterThan(headWidth(0.1));
    expect(headWidth(CHIN_Y + 0.02)).toBeLessThan(0.15);
    expect(headWidth(TOP_Y + 0.1)).toBe(0);
    expect(figureWidth(-1.5)).toBeGreaterThan(1.2); // shoulders
  });

  it("mountain noise is bounded", () => {
    for (let i = 0; i < 200; i++) {
      const value = ridges(i * 0.37, -i * 0.21, 3);
      expect(value).toBeGreaterThanOrEqual(0);
      expect(value).toBeLessThanOrEqual(1);
    }
  });
});

it("holographic profile keeps contour anatomy and voice light without illustrative facial features", () => {
  const figure = buildFigure({ quality: "low", terrain: true, style: "holographic" });
  for (const part of ["eye", "lid", "brow", "mouth"] as const) expect(figure.counts[part]).toBe(0);
  for (const part of ["head", "body", "core", "terrain"] as const) expect(figure.counts[part]).toBeGreaterThan(0);
  expect(figure.positions.every(Number.isFinite)).toBe(true);
});
