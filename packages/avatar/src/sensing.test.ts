import { describe, expect, it } from "vitest";
import type { Gaze } from "./avatar";
import { MotionAdapter, type AttentionView } from "./sensing";
import { simulatedIntent } from "./sensing.fixtures";

// All engine intents here are SIMULATED fixtures: these tests prove the adapter's rules
// (engine first, labelled pointer fallback, hidden/stop release), not any camera. The
// arbitration itself (face/hand/mode, smoothing, staleness) lives in the engine's
// AttentionController and is tested in packages/face-tracking.

function harness() {
  const gazes: (Gaze | null)[] = [];
  const views: AttentionView[] = [];
  const adapter = new MotionAdapter({ setGaze: (g) => gazes.push(g ? { ...g } : null) }, { onChange: (v) => views.push(v) });
  return { adapter, gazes, views };
}

describe("MotionAdapter", () => {
  it("applies the engine's intent to the figure and reports its source and state", () => {
    const h = harness();
    h.adapter.apply(simulatedIntent("face", 0.4, -0.1, 100, "following_head"));
    expect(h.gazes.at(-1)).toEqual({ yaw: 0.4, pitch: -0.1 });
    expect(h.adapter.view()).toEqual({ source: "face", state: "following_head", confidence: 0.8 });
    h.adapter.apply(simulatedIntent("hand", -0.7, 0.3, 120));
    expect(h.gazes.at(-1)).toEqual({ yaw: -0.7, pitch: 0.3 });
    expect(h.adapter.view().source).toBe("hand");
  });

  it("falls back to the pointer or touch, labelled as such, only while the engine is neutral", () => {
    const h = harness();
    h.adapter.pointerGaze({ yaw: 0.2, pitch: -0.1 }, "touch");
    expect(h.adapter.view()).toEqual({ source: "touch", state: "neutral", confidence: 1 });
    expect(h.gazes.at(-1)).toEqual({ yaw: 0.2, pitch: -0.1 });
    h.adapter.apply(simulatedIntent("face", 0.5, 0, 100));
    expect(h.adapter.view().source).toBe("face"); // the engine wins over the pointer
    h.adapter.apply(simulatedIntent("neutral", 0, 0, 200, "attention_lost"));
    expect(h.adapter.view()).toEqual({ source: "touch", state: "attention_lost", confidence: 1 });
    h.adapter.pointerGaze(null);
    expect(h.gazes.at(-1)).toBeNull();
    expect(h.adapter.view().source).toBe("none");
  });

  it("never moves the figure while hidden, and stop() lets go of everything", () => {
    const h = harness();
    h.adapter.setVisible(false);
    h.adapter.apply(simulatedIntent("face", 0.5, 0, 100));
    h.adapter.pointerGaze({ yaw: 0.1, pitch: 0.1 });
    expect(h.gazes.filter(Boolean)).toEqual([]);
    expect(h.adapter.view().state).toBe("hidden");
    h.adapter.setVisible(true);
    h.adapter.apply(simulatedIntent("face", 0.5, 0, 200));
    expect(h.adapter.view().source).toBe("face");
    h.adapter.stop();
    expect(h.gazes.at(-1)).toBeNull();
    expect(h.views.at(-1)).toEqual({ source: "none", state: "stopped", confidence: 0 });
    h.adapter.apply(simulatedIntent("face", 0.2, 0, 300));
    expect(h.adapter.view().source).toBe("face"); // a new engine intent resumes
  });

  it("clamps and ignores non-finite numbers, and only calls the figure when the gaze really changed", () => {
    const h = harness();
    h.adapter.apply({ ...simulatedIntent("face", 3, Number.NaN, 100), confidence: 5 });
    expect(h.gazes.at(-1)).toEqual({ yaw: 1, pitch: 0 });
    const calls = h.gazes.length;
    for (let i = 0; i < 20; i++) h.adapter.apply(simulatedIntent("face", 1, 0.001 * (i % 2), 110 + i));
    expect(h.gazes.length).toBe(calls);
    expect(h.views.length).toBe(1); // onChange fires on source/state changes, not every frame
  });
});
