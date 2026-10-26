import { describe, expect, it } from "vitest";
import { DEFAULT_VAD, rmsOf, speakingSeconds, vadStart, vadStep, type VadAction, type VadConfig } from "./vad";

const config: VadConfig = { threshold: 0.1, endSilenceMs: 1000, noSpeechMs: 3000, maxMs: 10_000 };

function feed(levels: [number, number][]): VadAction[] {
  let state = vadStart(0);
  return levels.map(([time, rms]) => {
    const [next, action] = vadStep(state, rms, time, config);
    state = next;
    return action;
  });
}

describe("voice activity detection", () => {
  it("ends the utterance after a pause that follows speech", () => {
    expect(feed([[100, 0.01], [500, 0.3], [900, 0.25], [1500, 0.02], [1950, 0.01]])).toEqual([
      "continue", "continue", "continue", "continue", "end",
    ]);
  });

  it("short pauses inside speech do not end it", () => {
    expect(feed([[100, 0.3], [600, 0.0], [1000, 0.3], [1900, 0.0]])).toEqual(["continue", "continue", "continue", "continue"]);
  });

  it("reports no speech when the user says nothing", () => {
    expect(feed([[1000, 0.01], [2999, 0.02], [3000, 0.01]])).toEqual(["continue", "continue", "no-speech"]);
  });

  it("stops at the maximum length", () => {
    expect(feed([[100, 0.5], [10_000, 0.5]])).toEqual(["continue", "end"]);
  });

  it("computes RMS", () => {
    expect(rmsOf(new Float32Array([0.5, -0.5, 0.5, -0.5]))).toBeCloseTo(0.5);
    expect(rmsOf(new Float32Array())).toBe(0);
  });

  it("measures speaking time from the first speech to the last loud moment", () => {
    expect(speakingSeconds(vadStart(0))).toBeNull();
    let state = vadStart(0);
    for (const [now, rms] of [[500, 0.01], [1000, 0.5], [3400, 0.5], [3500, 0.01], [4600, 0.01]] as const) {
      state = vadStep(state, rms, now)[0];
    }
    expect(speakingSeconds(state)).toBe(2.4);
  });
});

describe("long exam answers", () => {
  it("a 2.5 s pause ends a chat utterance but not an IELTS long turn", async () => {
    const { LONG_ANSWER_VAD } = await import("./engine");
    const run = (config: typeof DEFAULT_VAD) => {
      let state = vadStart(0);
      let action: VadAction = "continue";
      for (let t = 0; t <= 4000 && action === "continue"; t += 100) {
        const loud = t < 1500; // 1.5 s of speech, then silence
        [state, action] = vadStep(state, loud ? 0.1 : 0, t, config);
        if (t === 4000) break;
      }
      return action;
    };
    expect(run(DEFAULT_VAD)).toBe("end");
    expect(run(LONG_ANSWER_VAD)).toBe("continue");
    expect(LONG_ANSWER_VAD.maxMs).toBeGreaterThanOrEqual(120_000);
  });
});
