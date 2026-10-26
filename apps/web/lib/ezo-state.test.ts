import { describe, expect, it } from "vitest";
import {
  EZO_STATES,
  nextEzoState,
  presenceLook,
  stageToState,
  voicePresence,
  type EzoEvent,
  type EzoState,
} from "./ezo-state";

function run(events: EzoEvent[], from: EzoState = "idle"): EzoState[] {
  const states: EzoState[] = [];
  let state = from;
  for (const event of events) {
    state = nextEzoState(state, event);
    states.push(state);
  }
  return states;
}

describe("EZO visible state", () => {
  it("follows a researched answer: thinking → searching → reading → speaking → completed → idle", () => {
    expect(
      run([
        { type: "send" },
        { type: "activity", stage: "searching" },
        { type: "activity", stage: "reading" },
        { type: "delta" },
        { type: "delta" },
        { type: "done" },
        { type: "settle" },
      ]),
    ).toEqual(["thinking", "searching", "reading", "speaking", "speaking", "completed", "idle"]);
  });

  it("shows errors and keeps them until settled", () => {
    expect(run([{ type: "send" }, { type: "error" }, { type: "delta" }, { type: "stopped" }])).toEqual([
      "thinking",
      "error",
      "error",
      "error",
    ]);
    expect(nextEzoState("error", { type: "settle" })).toBe("idle");
  });

  it("returns to idle when the user stops a reply", () => {
    expect(run([{ type: "send" }, { type: "delta" }, { type: "stopped" }])).toEqual(["thinking", "speaking", "idle"]);
  });

  it("settle does not interrupt an active state", () => {
    expect(nextEzoState("searching", { type: "settle" })).toBe("searching");
  });

  it("maps unknown server stages to working and never trusts arbitrary strings", () => {
    expect(stageToState("coding")).toBe("coding");
    expect(stageToState("researching")).toBe("working");
    expect(stageToState("<script>")).toBe("working");
    expect(stageToState("completed")).toBe("working");
  });

  it("every state has a look; only active states are busy", () => {
    for (const state of EZO_STATES) {
      const look = presenceLook(state);
      expect(look.spin).toBeGreaterThan(0);
      expect(look.busy).toBe(!["idle", "completed", "error", "offline"].includes(state));
    }
    expect(presenceLook("error").tone).toBe("danger");
    expect(presenceLook("completed").tone).toBe("success");
  });

  it("voice shows the microphone/speech phase, and server stages while preparing a reply", () => {
    expect(voicePresence("listening", "idle")).toBe("listening");
    expect(voicePresence("speaking", "completed")).toBe("speaking");
    expect(voicePresence("thinking", "searching")).toBe("searching");
    expect(voicePresence("thinking", "speaking")).toBe("thinking"); // text still arriving, not spoken yet
    expect(voicePresence("thinking", "error")).toBe("error");
    expect(voicePresence("idle", "error")).toBe("error");
    expect(voicePresence("idle", "completed")).toBe("idle");
  });
});
