import { afterEach, describe, expect, it } from "vitest";
import { getVoiceSignal, publishVoiceLevel, publishVoiceUnavailable, resetVoiceSignal, subscribeVoiceLevel } from "./level";
afterEach(() => resetVoiceSignal());
describe("voice signal provenance", () => {
  it("keeps microphone input separate from generated output and clamps samples", () => {
    const seen: string[] = [];
    const off = subscribeVoiceLevel((s) => seen.push(`${s.channel}:${s.level}:${s.measured}`));
    publishVoiceLevel(2, "microphone");
    expect(getVoiceSignal()).toEqual({ level: 1, channel: "microphone", measured: true, status: "live" });
    publishVoiceLevel(0.4, "output");
    expect(getVoiceSignal().channel).toBe("output");
    resetVoiceSignal("microphone");
    expect(getVoiceSignal().level).toBe(0.4); // another channel cannot clear output
    off();
    expect(seen).toEqual(["microphone:1:true", "output:0.4:true"]);
  });
  it("reports unavailable PCM as unavailable, never as a measured zero", () => {
    publishVoiceUnavailable("output");
    expect(getVoiceSignal()).toEqual({ level: 0, channel: "output", measured: false, status: "unavailable" });
    resetVoiceSignal("output");
    expect(getVoiceSignal().status).toBe("idle");
  });
});
