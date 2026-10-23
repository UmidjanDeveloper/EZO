import { describe, expect, it } from "vitest";
import { followLevel, levelFromSamples, syntheticSpeech } from "./level";
import { frameCamera, project } from "./math";
import { AVATAR_STATES, easeLook, lookFor, toAvatarState } from "./states";

describe("states", () => {
  it("maps every EZO activity to a look", () => {
    expect(toAvatarState("searching")).toBe("thinking");
    expect(toAvatarState("completed")).toBe("idle");
    expect(toAvatarState("speaking")).toBe("speaking");
    expect(toAvatarState("unknown")).toBe("idle");
  });

  it("speaking is the warmest look, error the coldest", () => {
    const warmth = AVATAR_STATES.map((s) => lookFor(s).warmth);
    expect(Math.max(...warmth)).toBe(lookFor("speaking").warmth);
    expect(Math.min(...warmth)).toBe(lookFor("error").warmth);
  });

  it("eases towards the target without overshooting", () => {
    let look = lookFor("idle");
    for (let i = 0; i < 120; i++) look = easeLook(look, lookFor("speaking"), 1 / 60);
    expect(look.speak).toBeGreaterThan(0.99);
    expect(look.speak).toBeLessThanOrEqual(1);
  });
});

describe("level", () => {
  it("maps silence to 0 and loud speech to 1", () => {
    expect(levelFromSamples(new Float32Array(256))).toBe(0);
    expect(levelFromSamples(new Float32Array(256).fill(0.5))).toBe(1);
    const quiet = levelFromSamples(new Float32Array(256).fill(0.01));
    expect(quiet).toBeGreaterThan(0);
    expect(quiet).toBeLessThan(0.5);
  });

  it("attacks faster than it releases", () => {
    const up = followLevel(0, 1, 0.05);
    const down = 1 - followLevel(1, 0, 0.05);
    expect(up).toBeGreaterThan(down);
  });

  it("synthetic speech stays in range", () => {
    for (let t = 0; t < 10; t += 0.07) {
      const v = syntheticSpeech(t);
      expect(v).toBeGreaterThanOrEqual(0);
      expect(v).toBeLessThanOrEqual(1);
    }
  });
});

describe("camera", () => {
  it("keeps the whole head in view for both framings and aspect ratios", () => {
    for (const framing of ["bust", "head"] as const) {
      for (const aspect of [0.5, 1, 1.8]) {
        const { viewProjection } = frameCamera(framing, aspect);
        for (const [x, y] of [[0, 1.3], [0, 0.0], [0.5, 0.62], [-0.5, 0.62]] as const) {
          const [nx, ny] = project(viewProjection, x, y, 0);
          expect(Math.abs(ny), `${framing} ${aspect} y`).toBeLessThan(1);
          expect(Math.abs(nx), `${framing} ${aspect} x`).toBeLessThan(1);
        }
      }
    }
  });
});
