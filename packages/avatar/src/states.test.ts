import { describe, expect, it } from "vitest";
import { followLevel, levelFromSamples, syntheticSpeech } from "./level";
import { frameCamera, project } from "./math";
import { AVATAR_STATES, easeLook, lookFor, toAvatarState, TRANSIENT_STATES } from "./states";

describe("states", () => {
  it("maps every EZO activity to a look", () => {
    expect(toAvatarState("searching")).toBe("working"); // real tool activity, not just thinking
    expect(toAvatarState("thinking")).toBe("thinking");
    expect(toAvatarState("transcribing")).toBe("recognizing");
    expect(toAvatarState("completed")).toBe("success");
    expect(toAvatarState("disconnected")).toBe("offline");
    expect(toAvatarState("speaking")).toBe("speaking");
    expect(toAvatarState("unknown")).toBe("idle");
  });

  it("has nine distinct looks: speaking warmest, offline coldest, success a moment only", () => {
    expect(AVATAR_STATES).toHaveLength(9);
    const warmth = AVATAR_STATES.map((s) => lookFor(s).warmth);
    expect(Math.max(...warmth)).toBe(lookFor("speaking").warmth);
    expect(Math.min(...warmth)).toBe(lookFor("offline").warmth);
    expect(lookFor("working").work).toBe(1);
    expect(lookFor("thinking").work).toBe(0);
    expect(lookFor("recognizing").listen).toBeGreaterThan(0);
    expect(lookFor("recognizing").think).toBeGreaterThan(0);
    expect(TRANSIENT_STATES.success).toBeGreaterThan(0);
    expect(TRANSIENT_STATES.error).toBeUndefined(); // an error stays until the app clears it
    const keys = AVATAR_STATES.map((s) => JSON.stringify(lookFor(s)));
    expect(new Set(keys).size).toBe(keys.length);
  });

  it("eases towards the target without overshooting", () => {
    let look = lookFor("idle");
    for (let i = 0; i < 120; i++) look = easeLook(look, lookFor("speaking"), 1 / 60);
    expect(look.speak).toBeGreaterThan(0.99);
    expect(look.speak).toBeLessThanOrEqual(1);
    expect(look.offline).toBe(0);
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

describe("avatar without a browser", () => {
  it("accepts gaze, state and head aim on a canvas with no WebGL and no window", async () => {
    const { EzoAvatar } = await import("./avatar");
    const calls: Record<string, unknown>[] = [];
    const canvas = {
      width: 64,
      height: 64,
      dataset: {} as Record<string, string>,
      getBoundingClientRect: () => ({ width: 64, height: 64 }),
      getContext: () => null,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      setAttribute: (name: string, value: string) => calls.push({ name, value }),
    } as unknown as HTMLCanvasElement;
    const labels = { offline: "EZO oflayn" } as Record<string, string>;
    const avatar = new EzoAvatar(canvas, { reducedMotion: true, describe: (s) => labels[s] ?? `EZO ${s}` });
    expect(avatar.renderer).toBe("none");
    expect(calls).toContainEqual({ name: "role", value: "img" });
    avatar.setState("offline");
    expect(canvas.dataset.state).toBe("offline");
    expect(calls.at(-1)).toEqual({ name: "aria-label", value: "EZO oflayn" });
    avatar.setGaze({ yaw: 5, pitch: Number.NaN }); // clamped, never throws
    avatar.setHeadAim({ yawRadians: 0.1, pitchRadians: 0 });
    avatar.setHeadAim(null);
    avatar.destroy();
  });
});

describe("measured performance", () => {
  it("reports zeros before the loop ran and finite numbers afterwards; heap only where exposed", async () => {
    const { EzoAvatar } = await import("./avatar");
    const canvas = {
      width: 64,
      height: 64,
      dataset: {} as Record<string, string>,
      getBoundingClientRect: () => ({ width: 64, height: 64 }),
      getContext: () => null,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      setAttribute: () => undefined,
    } as unknown as HTMLCanvasElement;
    const avatar = new EzoAvatar(canvas, { reducedMotion: true, describe: (s) => s });
    expect(avatar.getPerformance()).toEqual({ frameMs: 0, drawMs: 0, fps: 0, heapMb: null });
    const memory = (performance as unknown as { memory?: unknown }).memory;
    (performance as unknown as { memory?: unknown }).memory = { usedJSHeapSize: 52_428_800 };
    try {
      expect(avatar.getPerformance().heapMb).toBe(50);
    } finally {
      (performance as unknown as { memory?: unknown }).memory = memory;
    }
    avatar.destroy();
  });
});
