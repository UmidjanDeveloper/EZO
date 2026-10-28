import { expect, it, vi } from "vitest";
import { ClapSession } from "./session";

// The session glue. The clap flow runs in Playwright with Chromium's fake microphone
// (tests/e2e/specs/perception.spec.ts).

it("asks only for the microphone, only on the owner's press, and releases it on stop", async () => {
  const getUserMedia = vi.fn(async () => {
    throw new Error("NotAllowedError: denied");
  });
  vi.stubGlobal("document", { hidden: false, addEventListener: vi.fn(), removeEventListener: vi.fn() });
  vi.stubGlobal("isSecureContext", true);
  vi.stubGlobal("navigator", { mediaDevices: { getUserMedia } });
  vi.stubGlobal("addEventListener", vi.fn());
  vi.stubGlobal("removeEventListener", vi.fn());
  const session = new ClapSession({ microphoneIndicator: {} as HTMLElement });
  try {
    expect(getUserMedia).not.toHaveBeenCalled();
    await session.startClap();
    expect(getUserMedia).toHaveBeenCalledExactlyOnceWith({ video: false, audio: expect.any(Object) });
    expect(session.diagnostics()).toMatchObject({ microphone: "error", lastError: "NotAllowedError: denied" });
  } finally {
    session.stop();
    vi.unstubAllGlobals();
  }
});
