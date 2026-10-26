/**
 * The voice frame: a thin ring, an equaliser and a state word around EZO's humanoid.
 *
 * Framework-free SVG built imperatively, so it runs in the web app, the Electron pill and
 * the Android WebView alike. The equaliser bars follow the avatar's drawn level (a real
 * measurement when one exists) rather than a timed animation; the ring breathes and turns
 * with the state. Design pattern (ring + waveform + state word, state-driven dashed
 * orbit) adapted from the MIT-licensed APEX-UI orb; drawn afresh in EZO's own palette,
 * with no Apex code, branding or assets. See packages/avatar/NOTICE.md.
 */
import type { EzoAvatar } from "./avatar";
import type { AvatarState } from "./states";

const NS = "http://www.w3.org/2000/svg";
const SIZE = 400; // viewBox; the element scales
const CENTER = SIZE / 2;
const RING = 150;
const BARS = 24;

/** Ring colour per state. Cyan/blue is EZO's figure; gold is its voice light. */
const COLORS: Record<AvatarState, string> = {
  idle: "#4fb3ff",
  listening: "#ff6e7a",
  recognizing: "#ffb15b",
  thinking: "#9b8cff",
  working: "#ffc94a",
  speaking: "#ffb65b",
  success: "#ffd36b",
  error: "#ff4d5a",
  offline: "#6b7585",
};

export interface VoiceFrameOptions {
  /** State word in the app's language; omitted states show nothing. */
  words?: Partial<Record<AvatarState, string>>;
  /** Hide the state word (e.g. when the app shows its own status line). */
  showWord?: boolean;
}

export interface VoiceFrame {
  readonly element: SVGSVGElement;
  setState(state: AvatarState): void;
  /** Level 0..1; call per frame. `live` marks a real measurement (bars are drawn solid). */
  setLevel(level: number, live?: boolean): void;
  /** Follow an avatar: its state, and its drawn level, every animation frame. */
  follow(avatar: EzoAvatar): void;
  destroy(): void;
}

function el<K extends keyof SVGElementTagNameMap>(tag: K, attrs: Record<string, string | number>): SVGElementTagNameMap[K] {
  const node = document.createElementNS(NS, tag);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, String(value));
  return node;
}

/** Deterministic per-bar weights so the equaliser has a shape, not a flat block. */
function weight(i: number): number {
  const x = (i / (BARS - 1)) * 2 - 1;
  return 0.35 + 0.65 * Math.exp(-x * x * 2.2) * (0.75 + 0.25 * Math.sin(i * 1.7));
}

export function createVoiceFrame(container: HTMLElement, options: VoiceFrameOptions = {}): VoiceFrame {
  const svg = el("svg", { viewBox: `0 0 ${SIZE} ${SIZE}`, "aria-hidden": "true", class: "ezo-voice-frame" });
  svg.style.position = "absolute";
  svg.style.inset = "0";
  svg.style.width = "100%";
  svg.style.height = "100%";
  svg.style.pointerEvents = "none";
  svg.style.overflow = "visible";

  const reduced = typeof window !== "undefined" && typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const outer = [RING + 22, RING + 40, RING + 58].map((r, i) =>
    el("circle", { cx: CENTER, cy: CENTER, r, fill: "none", "stroke-width": i === 0 ? 0.8 : 0.5, "stroke-dasharray": i % 2 ? "3 9" : "none", opacity: 0.22 - i * 0.05 }),
  );
  const orbit = el("circle", { cx: CENTER, cy: CENTER, r: RING + 11, fill: "none", "stroke-width": 1, "stroke-dasharray": "8 14", opacity: 0 });
  const glow = el("circle", { cx: CENTER, cy: CENTER, r: RING, fill: "none", "stroke-width": 10, opacity: 0.1 });
  const ring = el("circle", { cx: CENTER, cy: CENTER, r: RING, fill: "none", "stroke-width": 2, opacity: 0.9 });
  const ticks = [0, 90, 180, 270].map((deg) => {
    const a = (deg * Math.PI) / 180;
    const r1 = RING + 66;
    return el("line", { x1: CENTER + Math.cos(a) * (r1 - 6), y1: CENTER + Math.sin(a) * (r1 - 6), x2: CENTER + Math.cos(a) * (r1 + 6), y2: CENTER + Math.sin(a) * (r1 + 6), "stroke-width": 1, opacity: 0.3 });
  });

  const barWidth = 3;
  const span = 150;
  const gap = (span - BARS * barWidth) / (BARS - 1);
  const bars = Array.from({ length: BARS }, (_, i) =>
    el("rect", { x: CENTER - span / 2 + i * (barWidth + gap), y: CENTER + RING + 24, width: barWidth, height: 3, rx: 1.5, opacity: 0.35 }),
  );
  const word = el("text", { x: CENTER, y: CENTER + RING + 62, "text-anchor": "middle", "font-size": 11, "letter-spacing": "0.28em", "font-family": "ui-monospace, 'Cascadia Mono', 'Roboto Mono', monospace", opacity: 0.7 });

  for (const node of [...outer, orbit, glow, ring, ...ticks, ...bars, word]) svg.append(node);
  container.append(svg);

  let state: AvatarState = "idle";
  let color = COLORS.idle;
  let frame = 0;
  let following: EzoAvatar | null = null;
  let angle = 0;
  let last = 0;

  const paint = () => {
    for (const node of [...outer, orbit, glow, ring, ...ticks]) node.setAttribute("stroke", color);
    for (const bar of bars) bar.setAttribute("fill", color);
    word.setAttribute("fill", color);
  };

  const setState = (next: AvatarState) => {
    state = next;
    color = COLORS[next];
    paint();
    orbit.setAttribute("opacity", next === "thinking" || next === "working" || next === "recognizing" ? "0.45" : "0");
    glow.setAttribute("opacity", next === "idle" || next === "offline" ? "0.08" : "0.2");
    ring.setAttribute("opacity", next === "offline" ? "0.35" : "0.9");
    const text = options.showWord === false ? "" : (options.words?.[next] ?? "");
    word.textContent = text;
    svg.dataset.state = next;
  };

  const setLevel = (level: number, live = true) => {
    const l = Math.min(1, Math.max(0, Number.isFinite(level) ? level : 0));
    const active = state !== "idle" && state !== "offline";
    for (let i = 0; i < BARS; i++) {
      const h = 3 + (active ? 6 + 30 * l * weight(i) : 4 * l * weight(i));
      const bar = bars[i]!;
      bar.setAttribute("height", h.toFixed(1));
      bar.setAttribute("y", (CENTER + RING + 24 + (34 - h) / 2).toFixed(1));
      bar.setAttribute("opacity", active ? (live ? "0.9" : "0.55") : "0.35");
    }
  };

  const tick = (now: number) => {
    if (!following) return;
    const dt = Math.min(0.1, (now - last) / 1000 || 0);
    last = now;
    const next = following.getState();
    if (next !== state) setState(next);
    setLevel(following.getLevel(), following.hasLiveLevel());
    if (!reduced) {
      angle = (angle + dt * (state === "working" ? 60 : state === "thinking" || state === "recognizing" ? 25 : 6)) % 360;
      orbit.setAttribute("transform", `rotate(${angle.toFixed(1)} ${CENTER} ${CENTER})`);
      ring.setAttribute("transform", `rotate(${(-angle * 0.3).toFixed(1)} ${CENTER} ${CENTER})`);
      ring.setAttribute("stroke-dasharray", state === "listening" ? "none" : "720 220");
    }
    frame = requestAnimationFrame(tick);
  };

  setState("idle");
  setLevel(0, false);

  return {
    element: svg,
    setState,
    setLevel,
    follow(avatar) {
      following = avatar;
      cancelAnimationFrame(frame);
      last = performance.now();
      frame = requestAnimationFrame(tick);
    },
    destroy() {
      following = null;
      cancelAnimationFrame(frame);
      svg.remove();
    },
  };
}
