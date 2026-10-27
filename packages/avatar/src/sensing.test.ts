import { describe, expect, it } from "vitest";
import type { Gaze } from "./avatar";
import { AttentionDriver, type MotionIntent } from "./sensing";
import { simulatedHand, simulatedHeadFrame, simulatedVision } from "./sensing.fixtures";

// All sensing inputs here are SIMULATED fixtures (sensing.fixtures.ts): these tests prove
// the driver's rules, not any camera.

function harness(options: { staleMs?: number } = {}) {
  let now = 1000;
  const gazes: (Gaze | null)[] = [];
  const intents: MotionIntent[] = [];
  const driver = new AttentionDriver({ setGaze: (g) => gazes.push(g ? { ...g } : null) }, { now: () => now, onIntent: (i) => intents.push(i), ...options });
  return { driver, gazes, intents, advance: (ms: number) => (now += ms), clock: () => now };
}

describe("AttentionDriver", () => {
  it("looks where the tracked face is, only while the camera reports tracking", () => {
    const h = harness();
    h.driver.headFrame(simulatedHeadFrame(h.clock(), Math.PI / 2));
    expect(h.driver.intent()).toEqual({ kind: "rest", source: "none" }); // camera off: frames are ignored
    expect(h.gazes).toEqual([]);
    h.driver.setVision(simulatedVision("tracking", h.clock()));
    h.driver.headFrame(simulatedHeadFrame(h.clock(), Math.PI / 2));
    expect(h.driver.intent()).toMatchObject({ kind: "look", source: "head" });
    expect(h.gazes.at(-1)!.yaw).toBeCloseTo(0.6);
  });

  it("releases the gaze when frames go stale, and when the face is lost", () => {
    const h = harness({ staleMs: 300 });
    h.driver.setVision(simulatedVision("tracking", h.clock()));
    h.driver.headFrame(simulatedHeadFrame(h.clock(), 1));
    h.advance(200);
    h.driver.tick();
    expect(h.driver.intent().kind).toBe("look");
    h.advance(200);
    h.driver.tick();
    expect(h.driver.intent()).toEqual({ kind: "rest", source: "stale" });
    expect(h.gazes.at(-1)).toBeNull();
    h.driver.headFrame(simulatedHeadFrame(h.clock(), 1));
    h.driver.headFrame(null);
    expect(h.driver.intent()).toEqual({ kind: "rest", source: "none" });
  });

  it("ignores low-confidence frames and frames that are already old when they arrive", () => {
    const h = harness();
    h.driver.setVision(simulatedVision("tracking", h.clock()));
    h.driver.headFrame(simulatedHeadFrame(h.clock(), 1, 0.3));
    expect(h.driver.intent().kind).toBe("rest");
    h.driver.headFrame(simulatedHeadFrame(h.clock() - 2000, 1, 1));
    expect(h.driver.intent().kind).toBe("rest");
    h.driver.headFrame({ ...simulatedHeadFrame(h.clock(), 1), yaw: Number.NaN, gazeX: Number.NaN });
    expect(h.gazes.at(-1)).toEqual({ yaw: 0, pitch: 0.2 * Math.cos(0.7) }); // never NaN
  });

  it("a raised hand wins over the head and keeps attention for a moment", () => {
    const h = harness();
    h.driver.setVision(simulatedVision("tracking", h.clock(), 1, 1));
    h.driver.headFrame(simulatedHeadFrame(h.clock(), Math.PI / 2));
    h.driver.handFrame(simulatedHand(h.clock(), -0.8, 0.4));
    expect(h.driver.intent()).toMatchObject({ kind: "look", source: "hand", target: { yaw: -0.8, pitch: 0.4 } });
    h.driver.handFrame(simulatedHand(h.clock(), -0.8, 0.4, false)); // lowered: not a target
    expect(h.driver.intent()).toMatchObject({ source: "head" });
    h.driver.handFrame(simulatedHand(h.clock(), 0.5, 0));
    h.advance(1000);
    h.driver.headFrame(simulatedHeadFrame(h.clock(), 0));
    expect(h.driver.intent()).toMatchObject({ source: "hand" }); // still held
    h.advance(400);
    h.driver.headFrame(simulatedHeadFrame(h.clock(), 0));
    expect(h.driver.intent()).toMatchObject({ source: "head" });
  });

  it("falls back to the pointer or touch, labelled as such, and rests when nothing is there", () => {
    const h = harness();
    h.driver.pointerGaze({ yaw: 0.2, pitch: -0.1 }, "touch");
    expect(h.driver.intent()).toEqual({ kind: "look", target: { yaw: 0.2, pitch: -0.1 }, source: "touch", confidence: 1 });
    h.driver.setVision(simulatedVision("denied", h.clock()));
    expect(h.driver.intent()).toMatchObject({ source: "touch" });
    h.driver.pointerGaze(null);
    expect(h.driver.intent()).toEqual({ kind: "rest", source: "camera-off" });
  });

  it("never tracks while hidden, and stop() lets go of everything", () => {
    const h = harness();
    h.driver.setVision(simulatedVision("tracking", h.clock()));
    h.driver.setVisible(false);
    h.driver.headFrame(simulatedHeadFrame(h.clock(), 1));
    h.driver.handFrame(simulatedHand(h.clock(), 0.5, 0.5));
    expect(h.driver.intent()).toEqual({ kind: "rest", source: "hidden" });
    expect(h.gazes.filter(Boolean)).toEqual([]);
    h.driver.setVisible(true);
    h.driver.headFrame(simulatedHeadFrame(h.clock(), 1));
    expect(h.driver.intent().kind).toBe("look");
    h.driver.stop();
    expect(h.gazes.at(-1)).toBeNull();
    expect(h.intents.at(-1)).toEqual({ kind: "rest", source: "stopped" });
  });

  it("ignores jitter below the deadband so the head does not twitch", () => {
    const h = harness();
    h.driver.setVision(simulatedVision("tracking", h.clock()));
    h.driver.headFrame({ ...simulatedHeadFrame(h.clock(), 0), gazeX: 0.5, gazeY: 0 });
    const before = h.gazes.length;
    for (let i = 0; i < 10; i++) h.driver.headFrame({ ...simulatedHeadFrame(h.clock(), 0), gazeX: 0.5 + 0.01 * (i % 2 ? 1 : -1), gazeY: 0 });
    expect(h.gazes.length).toBe(before);
    h.driver.headFrame({ ...simulatedHeadFrame(h.clock(), 0), gazeX: 0.6, gazeY: 0 });
    expect(h.gazes.length).toBe(before + 1);
  });
});
