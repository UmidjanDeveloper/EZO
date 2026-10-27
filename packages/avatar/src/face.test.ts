import { describe, expect, it } from "vitest";
import { BLINK_LENGTH, blinkCurve, browFor, droopFor, eyeTarget, mouthFor, nextBlinkDelay, smileFor } from "./face";
import { buildFigure, EYE, eyeOutline, KIND } from "./figure";
import { lookFor } from "./states";

describe("face", () => {
  it("blinks: shut in the middle, open at both ends, never outside 0..1", () => {
    expect(blinkCurve(-1)).toBe(0);
    expect(blinkCurve(0)).toBe(0);
    expect(blinkCurve(0.09)).toBe(1);
    expect(blinkCurve(BLINK_LENGTH)).toBe(0);
    for (let t = 0; t < BLINK_LENGTH; t += 0.005) {
      const v = blinkCurve(t);
      expect(v).toBeGreaterThanOrEqual(0);
      expect(v).toBeLessThanOrEqual(1);
    }
  });

  it("blinks every 2–6 s, more often when attentive", () => {
    expect(nextBlinkDelay(0, 0)).toBeCloseTo(2.2);
    expect(nextBlinkDelay(1, 0)).toBeCloseTo(6);
    expect(nextBlinkDelay(0.5, 1)).toBeLessThan(nextBlinkDelay(0.5, 0));
  });

  it("eyes follow a tracked gaze further than the head, else wander and look up while thinking", () => {
    expect(eyeTarget(lookFor("idle"), { yaw: 0.4, pitch: -0.2 }, 0)).toEqual({ yaw: 0.5, pitch: -0.25 });
    expect(eyeTarget(lookFor("idle"), { yaw: 2, pitch: 0 }, 0).yaw).toBe(1); // clamped
    const idle = eyeTarget(lookFor("idle"), null, 3);
    expect(Math.abs(idle.yaw)).toBeLessThan(0.3);
    const thinking = eyeTarget(lookFor("thinking"), null, 3);
    expect(thinking.pitch).toBeGreaterThan(0.5);
    expect(thinking.yaw).toBeGreaterThan(0.3);
  });

  it("mouth opens only with the voice, and only while speaking", () => {
    expect(mouthFor(0, lookFor("speaking"))).toBe(0);
    expect(mouthFor(0.6, lookFor("speaking"))).toBeGreaterThan(0.5);
    expect(mouthFor(0.6, lookFor("speaking"))).toBeLessThanOrEqual(1);
    expect(mouthFor(0.9, lookFor("listening"))).toBe(0); // the microphone level never opens EZO's mouth
  });

  it("brows, lids and corners tell the states apart", () => {
    expect(browFor(lookFor("listening"))).toBeGreaterThan(0);
    expect(browFor(lookFor("thinking"))).toBeLessThan(0);
    expect(droopFor(lookFor("offline"))).toBeGreaterThan(0.4);
    expect(droopFor(lookFor("idle"))).toBe(0);
    expect(smileFor(lookFor("success"))).toBeGreaterThan(0.5);
    expect(smileFor(lookFor("error"))).toBeLessThan(0);
  });

  it("builds two eyes with iris and pupil, lids, brows and lips on the face surface", () => {
    const figure = buildFigure({ quality: "low", terrain: false });
    expect(figure.counts.eye).toBeGreaterThan(200);
    expect(figure.counts.lid).toBeGreaterThan(30);
    expect(figure.counts.brow).toBeGreaterThan(30);
    expect(figure.counts.mouth).toBeGreaterThan(60);
    let left = 0;
    let right = 0;
    let pupils = 0;
    for (let i = 0; i < figure.count; i++) {
      if (figure.data[i * 4] !== KIND.eye) continue;
      const x = figure.positions[i * 3]!;
      const y = figure.positions[i * 3 + 1]!;
      const z = figure.positions[i * 3 + 2]!;
      if (x < 0) left += 1;
      else right += 1;
      expect(Math.abs(Math.abs(x) - EYE.x)).toBeLessThan(EYE.rx + 0.01);
      expect(Math.abs(y - EYE.y)).toBeLessThan(EYE.ry + 0.01);
      expect(z).toBeGreaterThan(0.3); // in front of the head, not inside it
      if (figure.data[i * 4 + 3] === 1) pupils += 1;
    }
    expect(Math.abs(left - right)).toBeLessThan(left * 0.1);
    expect(pupils).toBeGreaterThan(40);
    expect(eyeOutline(0, true)).toBe(1);
    expect(eyeOutline(0, false)).toBeLessThan(0);
    expect(eyeOutline(1, true)).toBe(0);
  });
});
