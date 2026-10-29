// Standalone preview: `?state=speaking&framing=bust&level=0.6&frame=1&gaze=0.5,0.2`.
// Used for screenshots and the avatar state gallery test.
import { AVATAR_STATES, createVoiceFrame, EzoAvatar, type AvatarState } from "../src/index";

const params = new URLSearchParams(location.search);
const canvas = document.getElementById("stage") as HTMLCanvasElement;
const WORDS: Record<AvatarState, string> = {
  idle: "TAYYOR",
  listening: "TINGLAYAPMAN",
  recognizing: "TANIYAPMAN",
  thinking: "O‘YLAYAPMAN",
  working: "BAJARYAPMAN",
  speaking: "GAPIRYAPMAN",
  success: "BAJARILDI",
  error: "XATOLIK",
  offline: "OFLAYN",
};
const avatar = new EzoAvatar(canvas, {
  framing: params.get("framing") === "head" ? "head" : "bust",
  quality: (["high", "balanced", "low"].includes(params.get("quality") ?? "") ? params.get("quality") : "auto") as "high" | "balanced" | "low" | "auto",
  power: params.get("power") === "low" ? "low" : params.get("power") === "high" ? "high" : "auto",
  ...(params.has("reduced") ? { reducedMotion: params.get("reduced") === "1" } : {}),
  describe: (s) => `EZO: ${WORDS[s]}`,
});
const state = (params.get("state") ?? "idle") as AvatarState;
avatar.setState(AVATAR_STATES.includes(state) ? state : "idle");
const level = Number(params.get("level") ?? "NaN");
if (Number.isFinite(level)) setInterval(() => avatar.setLevel(level), 50);
const gaze = params.get("gaze")?.split(",").map(Number);
if (gaze && gaze.length === 2) setInterval(() => avatar.setGaze({ yaw: gaze[0]!, pitch: gaze[1]! }), 200);
if (params.get("frame") === "1") {
  const frame = createVoiceFrame(document.getElementById("frame") as HTMLElement, { words: WORDS });
  frame.follow(avatar);
}
(window as unknown as { avatar: EzoAvatar }).avatar = avatar;
document.body.dataset.renderer = avatar.renderer;
