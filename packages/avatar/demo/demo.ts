// Standalone preview: `?state=speaking&framing=bust&level=0.6`. Used for screenshots.
import { AVATAR_STATES, EzoAvatar, type AvatarState } from "../src/index";

const params = new URLSearchParams(location.search);
const canvas = document.getElementById("stage") as HTMLCanvasElement;
const avatar = new EzoAvatar(canvas, {
  framing: params.get("framing") === "head" ? "head" : "bust",
  quality: params.get("quality") === "low" ? "low" : "auto",
});
const state = (params.get("state") ?? "idle") as AvatarState;
avatar.setState(AVATAR_STATES.includes(state) ? state : "idle");
const level = Number(params.get("level") ?? "NaN");
if (Number.isFinite(level)) setInterval(() => avatar.setLevel(level * (0.7 + 0.3 * Math.random())), 50);
(window as unknown as { avatar: EzoAvatar }).avatar = avatar;
document.body.dataset.renderer = avatar.renderer;
