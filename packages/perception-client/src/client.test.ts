import { describe, expect, it, vi } from "vitest";
import { loadVisionAssets } from "./assets";
import { MotionAdapter } from "@ezo/avatar";
import { PerceptionSession, cameraState } from "./session";

// Pure parts of the client glue. The sessions themselves run in Playwright against the real
// engine with Chromium's fake media (tests/e2e/specs/perception.spec.ts).

describe("loadVisionAssets", () => {
  it("reports missing, invalid and network readiness honestly", async () => {
    const fetch404 = async () => new Response("", { status: 404 });
    expect(await loadVisionAssets("/vision/", fetch404 as unknown as typeof fetch)).toMatchObject({ ready: false, reason: "missing" });
    const fetchBad = async () => new Response(JSON.stringify({ face: { url: "https://cdn.example/x.task", sha256: "0".repeat(64) } }), { status: 200 });
    const invalid = await loadVisionAssets("https://app.example/vision/", fetchBad as unknown as typeof fetch);
    expect(invalid).toMatchObject({ ready: false, reason: "invalid" });
    const fetchDown = async () => {
      throw new Error("offline");
    };
    expect(await loadVisionAssets("/vision/", fetchDown as unknown as typeof fetch)).toMatchObject({ ready: false, reason: "network", detail: "offline" });
  });

  it("accepts a same-origin, correctly pinned manifest", async () => {
    const manifest = {
      face: { url: "https://app.example/vision/face_landmarker.task", sha256: "a".repeat(64) },
      hand: { url: "https://app.example/vision/hand_landmarker.task", sha256: "b".repeat(64) },
      wasmLoader: { url: "https://app.example/vision/vision_wasm_nosimd_internal.js", sha256: "9f8fc960e363f0fb2f42f7937b97ae9cf9a5630490f71031fa90caa9bb121938" },
      wasmBinary: { url: "https://app.example/vision/vision_wasm_nosimd_internal.wasm", sha256: "924274fcd5ac8985f6570a8573e7971b7bd2d580ba1b8f3beb0ba8f95db6347c" },
      modelLicenseReview: "reviewed",
    };
    const fetchOk = async () => new Response(JSON.stringify(manifest), { status: 200 });
    const result = await loadVisionAssets("https://app.example/vision/", fetchOk as unknown as typeof fetch);
    expect(result.ready).toBe(true);
  });
});

describe("cameraState", () => {
  it("maps the engine's words to the UI state; a refused permission reads as denied", () => {
    expect(cameraState("off")).toBe("off");
    expect(cameraState("tracking")).toBe("tracking");
    expect(cameraState("lost")).toBe("lost");
    expect(cameraState("error", "Camera permission revoked")).toBe("denied");
    expect(cameraState("error", "NotAllowedError: denied")).toBe("denied");
    expect(cameraState("error", "Vision deadline exceeded")).toBe("error");
  });
});

it("microphone consent is independent from missing camera models; camera remains fail closed", async () => {
  const getUserMedia=vi.fn(async()=>{throw new Error("NotAllowedError: denied");});
  vi.stubGlobal("document", {hidden:false,addEventListener:vi.fn(),removeEventListener:vi.fn()});
  vi.stubGlobal("isSecureContext",true);vi.stubGlobal("navigator",{mediaDevices:{getUserMedia}});
  vi.stubGlobal("addEventListener",vi.fn());vi.stubGlobal("removeEventListener",vi.fn());
  const session=new PerceptionSession({base:"/vision/",video:{pause:vi.fn()} as unknown as HTMLVideoElement,cameraIndicator:{} as HTMLElement,microphoneIndicator:{} as HTMLElement,adapter:new MotionAdapter({setGaze:vi.fn()})});
  try { await session.startCamera();expect(getUserMedia).not.toHaveBeenCalled();expect(session.visionStatus().camera).toBe("unavailable");await session.startClap();expect(getUserMedia).toHaveBeenCalledExactlyOnceWith({video:false,audio:expect.any(Object)}); } finally {session.stop();vi.unstubAllGlobals();}
});
