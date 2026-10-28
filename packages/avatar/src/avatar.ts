/**
 * EzoAvatar: mounts the humanoid on a <canvas> and animates it.
 *
 *   const avatar = new EzoAvatar(canvas, { framing: "bust" });
 *   avatar.setState("listening");
 *   avatar.setLevel(0.4); // optional: live microphone / voice level
 *   avatar.destroy();
 *
 * WebGL 1 with additive points; falls back to a still 2D drawing when WebGL is
 * unavailable. Respects prefers-reduced-motion (renders still frames only) and
 * pauses while the page is hidden.
 */
import { blinkCurve, BLINK_LENGTH, browFor, CLOSED_FACE, droopFor, eyeTarget, mouthFor, nextBlinkDelay, smileFor, type FaceAmounts } from "./face";
import { buildFigure, EYE, type Figure } from "./figure";
import { followLevel, syntheticSpeech } from "./level";
import { frameCamera, project, type Framing } from "./math";
import { MASK_FRAGMENT, MASK_VERTEX, POINT_FRAGMENT, POINT_VERTEX } from "./shaders";
import { easeLook, lookFor, TRANSIENT_STATES, type AvatarState, type Look } from "./states";

export interface AvatarOptions {
  framing?: Framing;
  style?: "expressive" | "holographic";
  /** "auto" picks "low" for small views and dense phone screens. */
  quality?: "high" | "low" | "auto";
  /** Mountains behind the figure. Defaults to true for "bust", false for "head". */
  terrain?: boolean;
  /** Overrides the prefers-reduced-motion media query. */
  reducedMotion?: boolean;
  /** Accessible name per state, in the app's language; applied to the canvas as aria-label. */
  describe?: (state: AvatarState) => string;
  /**
   * Low-power mode halves the frame rate (30 fps cap) and stills the halo drift; "auto"
   * turns it on for devices that report little memory or a data-saver preference.
   */
  power?: "auto" | "low" | "high";
}

/** Where EZO looks, from the pointer or a touch. Normalised: -1 (left/down) .. 1. */
export interface Gaze {
  yaw: number;
  pitch: number;
}

/** How long a gaze stays before the head drifts back to its idle sway. */
const GAZE_HOLD_SECONDS = 1.5;

const UNIFORMS = [
  "uVP", "uTime", "uLevel", "uEnergy", "uWarmth", "uListen", "uThink", "uSpeak", "uError", "uWork", "uSuccess", "uOffline", "uYaw", "uPitch", "uPx", "uGlowPx", "uRef",
  "uBlink", "uDroop", "uEyeX", "uEyeY", "uBrow", "uMouth", "uSmile",
] as const;
const LOW_POWER_FRAME_MS = 1000 / 30;
type UniformName = (typeof UNIFORMS)[number];

interface GlState {
  gl: WebGLRenderingContext;
  points: WebGLProgram;
  mask: WebGLProgram;
  uniforms: Record<UniformName, WebGLUniformLocation | null>;
  maskVP: WebGLUniformLocation | null;
  maskYaw: WebGLUniformLocation | null;
  maskPitch: WebGLUniformLocation | null;
  buffers: WebGLBuffer[];
  attributes: { pos: number; data: number; extra: number; xy: number };
  silhouetteVertices: number;
}

const STILL_TIME = 6.5; // the moment shown when motion is reduced

function compile(gl: WebGLRenderingContext, vertex: string, fragment: string): WebGLProgram {
  const program = gl.createProgram();
  for (const [type, source] of [
    [gl.VERTEX_SHADER, vertex],
    [gl.FRAGMENT_SHADER, fragment],
  ] as const) {
    const shader = gl.createShader(type);
    if (!shader) throw new Error("shader allocation failed");
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
      throw new Error(`shader: ${gl.getShaderInfoLog(shader) ?? "compile failed"}`);
    }
    gl.attachShader(program, shader);
  }
  gl.linkProgram(program);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
    throw new Error(`program: ${gl.getProgramInfoLog(program) ?? "link failed"}`);
  }
  return program;
}

export class EzoAvatar {
  readonly canvas: HTMLCanvasElement;
  readonly framing: Framing;
  /** "webgl", "2d" (still fallback) or "none". */
  readonly renderer: "webgl" | "2d" | "none";

  private figure: Figure;
  private glState: GlState | null = null;
  private state: AvatarState = "idle";
  private look: Look = lookFor("idle");
  private level = 0;
  private levelTarget = 0;
  private levelAt = -Infinity;
  private gazeTarget: Gaze = { yaw: 0, pitch: 0 };
  private gaze: Gaze = { yaw: 0, pitch: 0 };
  private gazeAt = -Infinity;
  private stateAt = 0;
  private face: FaceAmounts = { ...CLOSED_FACE, eye: { yaw: 0, pitch: 0 } };
  private blinkStart = -Infinity;
  private nextBlink = 1.2;
  private lowPower = false;
  private active = true;
  private readonly describe: ((state: AvatarState) => string) | null;
  private time = 0;
  private last = 0;
  private frame = 0;
  private frames = 0;
  /** Measured loop cost: exponential averages of the display interval and of step+draw time (ms). */
  private frameMs = 0;
  private drawMs = 0;
  private running = false;
  private destroyed = false;
  private readonly reduced: boolean;
  private readonly observer: ResizeObserver | null;
  private readonly onVisibility = () => this.syncRunning();
  private readonly onLost = (event: Event) => {
    event.preventDefault();
    this.glState = null;
    this.stopLoop();
  };
  private readonly onRestored = () => {
    this.glState = this.initGl();
    this.syncRunning();
  };

  constructor(canvas: HTMLCanvasElement, options: AvatarOptions = {}) {
    this.canvas = canvas;
    this.framing = options.framing ?? "bust";
    const media = typeof window !== "undefined" && typeof window.matchMedia === "function" ? window.matchMedia("(prefers-reduced-motion: reduce)") : null;
    this.reduced = options.reducedMotion ?? media?.matches ?? false;
    this.describe = options.describe ?? null;
    const rect = canvas.getBoundingClientRect();
    // A canvas not laid out yet (e.g. inside a dialog that opens after this runs) measures 0x0: unknown, not small.
    const small = rect.width > 0 && rect.height > 0 && Math.max(rect.width, rect.height) < 260;
    const dense = typeof window !== "undefined" && (window.devicePixelRatio ?? 1) > 2.5;
    const quality = options.quality && options.quality !== "auto" ? options.quality : small || dense ? "low" : "high";
    this.lowPower = options.power === "low" || (options.power !== "high" && EzoAvatar.prefersLowPower());
    const started = typeof performance !== "undefined" ? performance.now() : 0;
    this.figure = buildFigure({ quality, terrain: options.terrain ?? this.framing === "bust", style: options.style });
    const buildMs = typeof performance !== "undefined" ? performance.now() - started : 0;

    this.glState = this.initGl();
    this.renderer = this.glState ? "webgl" : canvas.getContext("2d") ? "2d" : "none";
    canvas.dataset.ezoAvatar = this.renderer;
    // Static facts for performance checks (set once, never per frame).
    canvas.dataset.quality = quality;
    canvas.dataset.style = options.style ?? "expressive";
    canvas.dataset.points = String(this.figure.count);
    canvas.dataset.buildMs = buildMs.toFixed(1);
    canvas.dataset.power = this.lowPower ? "low" : "high";
    canvas.dataset.motion = this.reduced ? "reduced" : "full";
    canvas.dataset.state = this.state;
    this.label();
    canvas.addEventListener("webglcontextlost", this.onLost);
    canvas.addEventListener("webglcontextrestored", this.onRestored);
    if (typeof document !== "undefined") document.addEventListener("visibilitychange", this.onVisibility);
    this.observer = typeof ResizeObserver !== "undefined" ? new ResizeObserver(() => this.redrawIfStill()) : null;
    this.observer?.observe(canvas);
    this.syncRunning();
  }

  /** WebGL is usable on this device. */
  static supported(): boolean {
    if (typeof document === "undefined") return false;
    try {
      const canvas = document.createElement("canvas");
      return Boolean(canvas.getContext("webgl") ?? canvas.getContext("experimental-webgl"));
    } catch {
      return false;
    }
  }

  /** The device asks for economy: little memory, a data-saver preference or a coarse, dense phone screen. */
  static prefersLowPower(): boolean {
    if (typeof navigator === "undefined") return false;
    const nav = navigator as Navigator & { deviceMemory?: number; connection?: { saveData?: boolean }; hardwareConcurrency?: number };
    if (typeof nav.deviceMemory === "number" && nav.deviceMemory <= 4) return true;
    if (nav.connection?.saveData) return true;
    return typeof nav.hardwareConcurrency === "number" && nav.hardwareConcurrency <= 2;
  }

  /** Switch the 30 fps economy mode on or off at runtime (e.g. on battery). */
  setLowPower(on: boolean): void {
    this.lowPower = on;
    this.canvas.dataset.power = on ? "low" : "high";
  }

  isLowPower(): boolean {
    return this.lowPower;
  }

  /** A hidden host (an Electron window that is hidden, a collapsed stage) stops drawing entirely. */
  setActive(active: boolean): void {
    this.active = active;
    this.syncRunning();
  }

  /** Frames drawn so far (still redraws included): proves the loop survives a context loss. */
  getFrameCount(): number {
    return this.frames;
  }

  /**
   * Measured performance for Diagnostics: average display interval and step+draw cost in
   * milliseconds (0 until the loop has run), the resulting frames per second, and the JS heap in
   * MB where the browser exposes it (Chromium's non-standard `performance.memory`; null elsewhere).
   * Numbers only; nothing is uploaded.
   */
  getPerformance(): { frameMs: number; drawMs: number; fps: number; heapMb: number | null } {
    const memory = (performance as unknown as { memory?: { usedJSHeapSize?: number } }).memory;
    const heap = memory?.usedJSHeapSize;
    return {
      frameMs: Number(this.frameMs.toFixed(2)),
      drawMs: Number(this.drawMs.toFixed(2)),
      fps: this.frameMs > 0 ? Number((1000 / this.frameMs).toFixed(1)) : 0,
      heapMb: typeof heap === "number" && Number.isFinite(heap) ? Number((heap / 1048576).toFixed(1)) : null,
    };
  }

  /** The facial amounts drawn now (blink, eye direction, jaw…): for tests and the voice frame. */
  getFace(): FaceAmounts {
    return { ...this.face, eye: { ...this.face.eye } };
  }

  setState(state: AvatarState): void {
    if (state === this.state) return;
    this.state = state;
    this.stateAt = this.time;
    this.canvas.dataset.state = state;
    this.label();
    if (this.reduced || !this.running) {
      this.look = lookFor(state);
      this.redrawIfStill();
    }
  }

  /** The state as last set (transient states return to "idle" by themselves). */
  getState(): AvatarState {
    return this.state;
  }

  /** The level actually being drawn now: the live voice, or the speech rhythm animated in its place. */
  getLevel(): number {
    return this.level;
  }

  /** True while the drawn level comes from a real measurement (not the synthetic rhythm). */
  hasLiveLevel(): boolean {
    return this.time - this.levelAt < 0.4;
  }

  /** Live voice level 0..1 (microphone while listening, EZO's voice while speaking). */
  setLevel(level: number): void {
    this.levelTarget = Math.min(1, Math.max(0, Number.isFinite(level) ? level : 0));
    this.levelAt = this.time;
  }

  /** Turn the head towards a point (the pointer or a touch). Null, or silence for
   * 1.5 s, lets the head return to its own gentle sway. Never used as proof of a face. */
  setGaze(gaze: Gaze | null): void {
    if (!gaze) {
      this.gazeAt = -Infinity;
      return;
    }
    const clamp = (v: number) => Math.min(1, Math.max(-1, Number.isFinite(v) ? v : 0));
    this.gazeTarget = { yaw: clamp(gaze.yaw), pitch: clamp(gaze.pitch) };
    this.gazeAt = this.time;
    if (this.reduced || !this.running) this.redrawIfStill();
  }

  private label(): void {
    if (!this.describe) return;
    this.canvas.setAttribute("role", "img");
    this.canvas.setAttribute("aria-label", this.describe(this.state));
  }

  destroy(): void {
    this.destroyed = true;
    this.stopLoop();
    this.observer?.disconnect();
    this.canvas.removeEventListener("webglcontextlost", this.onLost);
    this.canvas.removeEventListener("webglcontextrestored", this.onRestored);
    if (typeof document !== "undefined") document.removeEventListener("visibilitychange", this.onVisibility);
    const glState = this.glState;
    if (glState) {
      const { gl } = glState;
      glState.buffers.forEach((buffer) => gl.deleteBuffer(buffer));
      gl.deleteProgram(glState.points);
      gl.deleteProgram(glState.mask);
    }
    this.glState = null;
  }

  // --- setup -------------------------------------------------------------------------------

  private initGl(): GlState | null {
    let gl: WebGLRenderingContext | null = null;
    try {
      gl = (this.canvas.getContext("webgl", { alpha: true, antialias: false, premultipliedAlpha: true, depth: true }) ??
        this.canvas.getContext("experimental-webgl")) as WebGLRenderingContext | null;
    } catch {
      gl = null;
    }
    if (!gl) return null;
    try {
      const points = compile(gl, POINT_VERTEX, POINT_FRAGMENT);
      const mask = compile(gl, MASK_VERTEX, MASK_FRAGMENT);
      const upload = (data: Float32Array) => {
        const buffer = gl.createBuffer();
        if (!buffer) throw new Error("buffer allocation failed");
        gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
        gl.bufferData(gl.ARRAY_BUFFER, data, gl.STATIC_DRAW);
        return buffer;
      };
      const buffers = [upload(this.figure.positions), upload(this.figure.data), upload(this.figure.extra), upload(this.figure.silhouette)];
      const uniforms = Object.fromEntries(UNIFORMS.map((name) => [name, gl.getUniformLocation(points, name)])) as GlState["uniforms"];
      return {
        gl,
        points,
        mask,
        uniforms,
        maskVP: gl.getUniformLocation(mask, "uVP"),
        maskYaw: gl.getUniformLocation(mask, "uYaw"),
        maskPitch: gl.getUniformLocation(mask, "uPitch"),
        buffers,
        attributes: {
          pos: gl.getAttribLocation(points, "aPos"),
          data: gl.getAttribLocation(points, "aData"),
          extra: gl.getAttribLocation(points, "aExtra"),
          xy: gl.getAttribLocation(mask, "aXY"),
        },
        silhouetteVertices: this.figure.silhouette.length / 2,
      };
    } catch (error) {
      console.warn("EZO avatar: WebGL setup failed, using the still fallback.", error);
      return null;
    }
  }

  // --- loop ----------------------------------------------------------------------------------

  private syncRunning(): void {
    const visible = typeof document === "undefined" || document.visibilityState !== "hidden";
    if (!this.destroyed && !this.reduced && this.glState && visible && this.active) this.startLoop();
    else {
      this.stopLoop();
      this.redrawIfStill();
    }
  }

  private startLoop(): void {
    if (this.running) return;
    this.running = true;
    this.last = performance.now();
    const tick = (now: number) => {
      if (!this.running) return;
      this.frame = requestAnimationFrame(tick);
      // Economy: skip every other display frame rather than draw a lighter figure.
      if (this.lowPower && now - this.last < LOW_POWER_FRAME_MS - 2) return;
      const dt = Math.min(0.1, Math.max(0, (now - this.last) / 1000));
      const interval = now - this.last;
      this.last = now;
      const started = performance.now();
      this.step(dt);
      this.draw();
      const cost = performance.now() - started;
      // Measured, not estimated: what the loop actually costs on this device (for Diagnostics).
      this.frameMs = this.frameMs ? this.frameMs * 0.9 + interval * 0.1 : interval;
      this.drawMs = this.drawMs ? this.drawMs * 0.9 + cost * 0.1 : cost;
    };
    this.frame = requestAnimationFrame(tick);
  }

  private stopLoop(): void {
    this.running = false;
    if (this.frame) cancelAnimationFrame(this.frame);
    this.frame = 0;
  }

  private step(dt: number): void {
    this.time += dt;
    const hold = TRANSIENT_STATES[this.state];
    if (hold !== undefined && this.time - this.stateAt > hold) this.setState("idle");
    this.look = easeLook(this.look, lookFor(this.state), dt);
    const held = this.time - this.gazeAt < GAZE_HOLD_SECONDS;
    const aim = held ? this.gazeTarget : { yaw: 0, pitch: 0 };
    const k = 1 - Math.exp(-dt * (held ? 6 : 1.5));
    this.gaze = { yaw: this.gaze.yaw + (aim.yaw - this.gaze.yaw) * k, pitch: this.gaze.pitch + (aim.pitch - this.gaze.pitch) * k };
    // Without a live level (e.g. the browser's own voice), speech gets a speech-like rhythm.
    const fresh = this.time - this.levelAt < 0.4;
    const target = fresh ? this.levelTarget : this.state === "speaking" ? syntheticSpeech(this.time) : this.state === "listening" ? 0.08 : 0;
    this.level = followLevel(this.level, target, dt);
    this.stepFace(dt, held ? this.gazeTarget : null);
  }

  /** Blinks, eye direction, brows and the jaw for this frame. */
  private stepFace(dt: number, gaze: Gaze | null): void {
    const look = this.look;
    if (this.time >= this.nextBlink && this.state !== "offline") {
      this.blinkStart = this.time;
      this.nextBlink = this.time + BLINK_LENGTH + nextBlinkDelay(Math.random(), look.listen);
    }
    const eye = eyeTarget(look, gaze, this.time);
    const k = 1 - Math.exp(-dt * 14); // the eyes move faster than the head
    const current = this.face.eye;
    this.face = {
      blink: blinkCurve(this.time - this.blinkStart),
      droop: droopFor(look),
      eye: { yaw: current.yaw + (eye.yaw - current.yaw) * k, pitch: current.pitch + (eye.pitch - current.pitch) * k },
      brow: browFor(look),
      mouth: mouthFor(this.level, look),
      smile: smileFor(look),
    };
  }

  private redrawIfStill(): void {
    if (this.running || this.destroyed) return;
    if (this.reduced || !this.glState) {
      this.time = STILL_TIME;
      this.level = this.state === "speaking" ? 0.5 : 0;
      const look = lookFor(this.state);
      const held = this.time - this.gazeAt < GAZE_HOLD_SECONDS;
      this.face = { blink: 0, droop: droopFor(look), eye: eyeTarget(look, held ? this.gazeTarget : null, 0), brow: browFor(look), mouth: mouthFor(this.level, look), smile: smileFor(look) };
    }
    this.draw();
  }

  // --- drawing -------------------------------------------------------------------------------

  private resize(): { width: number; height: number; cssHeight: number; dpr: number } {
    const rect = this.canvas.getBoundingClientRect();
    const dpr = Math.min(typeof window !== "undefined" ? window.devicePixelRatio || 1 : 1, 2);
    const width = Math.max(1, Math.round((rect.width || this.canvas.width) * dpr));
    const height = Math.max(1, Math.round((rect.height || this.canvas.height) * dpr));
    if (this.canvas.width !== width || this.canvas.height !== height) {
      this.canvas.width = width;
      this.canvas.height = height;
    }
    return { width, height, cssHeight: height / dpr, dpr };
  }

  private motion(): { yaw: number; pitch: number } {
    const t = this.time;
    const still = this.reduced || !this.running;
    const gaze = still && this.time - this.gazeAt < GAZE_HOLD_SECONDS ? this.gazeTarget : this.gaze;
    // Idle sway, plus up to ±0.35 rad of real gaze (listening leans in a little).
    const attention = 1 - 0.3 * this.look.listen;
    return {
      yaw: attention * (0.1 * Math.sin(t * 0.23) + 0.04 * Math.sin(t * 0.61)) + 0.35 * gaze.yaw,
      pitch: 0.03 * Math.sin(t * 0.17) + 0.2 * gaze.pitch,
    };
  }

  private draw(): void {
    if (this.destroyed) return;
    this.frames += 1;
    const { width, height, cssHeight, dpr } = this.resize();
    const camera = frameCamera(this.framing, width / height);
    if (!this.glState) {
      this.drawStill(camera.viewProjection, width, height);
      return;
    }
    const { gl, points, mask, uniforms: u, buffers, attributes, silhouetteVertices } = this.glState;
    const { yaw, pitch } = this.motion();
    gl.viewport(0, 0, width, height);
    gl.clearColor(0, 0, 0, 0);
    gl.clearDepth(1);
    gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
    gl.enable(gl.DEPTH_TEST);
    gl.depthFunc(gl.LESS);

    // 1. The silhouette writes depth only.
    gl.useProgram(mask);
    gl.colorMask(false, false, false, false);
    gl.depthMask(true);
    gl.disable(gl.BLEND);
    gl.uniformMatrix4fv(this.glState.maskVP, false, camera.viewProjection);
    gl.uniform1f(this.glState.maskYaw, yaw);
    gl.uniform1f(this.glState.maskPitch, pitch);
    gl.bindBuffer(gl.ARRAY_BUFFER, buffers[3]!);
    gl.enableVertexAttribArray(attributes.xy);
    gl.vertexAttribPointer(attributes.xy, 2, gl.FLOAT, false, 0, 0);
    gl.drawArrays(gl.TRIANGLES, 0, silhouetteVertices);
    gl.disableVertexAttribArray(attributes.xy);

    // 2. Glowing points, added together.
    gl.useProgram(points);
    gl.colorMask(true, true, true, true);
    gl.depthMask(false);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.ONE, gl.ONE);
    const look = this.look;
    gl.uniformMatrix4fv(u.uVP, false, camera.viewProjection);
    gl.uniform1f(u.uTime, this.time);
    gl.uniform1f(u.uLevel, this.level);
    gl.uniform1f(u.uEnergy, look.energy);
    gl.uniform1f(u.uWarmth, look.warmth);
    gl.uniform1f(u.uListen, look.listen);
    gl.uniform1f(u.uThink, look.think);
    gl.uniform1f(u.uSpeak, look.speak);
    gl.uniform1f(u.uError, look.error);
    gl.uniform1f(u.uWork, look.work);
    gl.uniform1f(u.uSuccess, look.success);
    gl.uniform1f(u.uOffline, look.offline);
    gl.uniform1f(u.uYaw, yaw);
    gl.uniform1f(u.uPitch, pitch);
    const face = this.face;
    gl.uniform1f(u.uBlink, face.blink);
    gl.uniform1f(u.uDroop, face.droop);
    gl.uniform1f(u.uEyeX, face.eye.yaw);
    gl.uniform1f(u.uEyeY, face.eye.pitch);
    gl.uniform1f(u.uBrow, face.brow);
    gl.uniform1f(u.uMouth, face.mouth);
    gl.uniform1f(u.uSmile, face.smile);
    // Point size follows the view size; small faces (pill, home screen) keep visible lines.
    const reference = this.framing === "head" ? 380 : 720;
    gl.uniform1f(u.uPx, dpr * Math.min(1.5, Math.max(0.6, cssHeight / reference)));
    gl.uniform1f(u.uGlowPx, dpr * Math.min(1.5, Math.max(0.1, cssHeight / reference)));
    gl.uniform1f(u.uRef, camera.distance);
    const bind = (index: number, location: number, size: number) => {
      gl.bindBuffer(gl.ARRAY_BUFFER, buffers[index]!);
      gl.enableVertexAttribArray(location);
      gl.vertexAttribPointer(location, size, gl.FLOAT, false, 0, 0);
    };
    bind(0, attributes.pos, 3);
    bind(1, attributes.data, 4);
    bind(2, attributes.extra, 2);
    gl.drawArrays(gl.POINTS, 0, this.figure.count);
    gl.disableVertexAttribArray(attributes.pos);
    gl.disableVertexAttribArray(attributes.data);
    gl.disableVertexAttribArray(attributes.extra);
  }

  /** No WebGL: a still drawing of the figure (no mountains), tinted by state. */
  private drawStill(viewProjection: Float32Array, width: number, height: number): void {
    const ctx = this.canvas.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, width, height);
    ctx.globalCompositeOperation = "lighter";
    const tint =
      this.state === "error" ? "255,70,80" : this.state === "offline" ? "90,100,120" : this.state === "success" ? "255,200,90" : "70,170,255";
    const warm = this.state === "speaking" || this.state === "success" ? "255,170,60" : this.state === "offline" ? "110,100,90" : "255,110,30";
    const { positions, data, extra, count } = this.figure;
    const dot = Math.max(1, height / 500);
    const face = this.face;
    for (let i = 0; i < count; i++) {
      const kind = data[i * 4]!;
      if (kind === 6 || kind === 3 || kind === 5) continue;
      let px = positions[i * 3]!;
      let py = positions[i * 3 + 1]!;
      const w = data[i * 4 + 3]!;
      let colour = w > 0.35 ? warm : tint;
      let alpha = 0.25 + 0.5 * data[i * 4 + 2]!;
      if (kind === 8) {
        // Eyes: the iris follows the gaze; the outline is the brightest line of the face.
        if (w > 0.25) {
          px += face.eye.yaw * 0.42 * EYE.rx;
          py += face.eye.pitch * 0.32 * EYE.ry;
        }
        colour = w > 0.75 ? "10,20,40" : w > 0.25 ? "80,190,255" : "190,235,255";
        alpha = w > 0.75 ? 0.9 : 0.85;
      } else if (kind === 9) {
        colour = "120,200,255";
      } else if (kind === 10) {
        colour = "90,160,255";
        py += face.brow * 0.02;
      } else if (kind === 11) {
        colour = "255,170,90";
        if (extra[i * 2 + 1]! > 0.5) py -= face.mouth * 0.06;
        alpha = 0.8;
      }
      const [x, y] = project(viewProjection, px, py, positions[i * 3 + 2]!);
      ctx.fillStyle = `rgba(${colour},${alpha})`;
      ctx.fillRect(((x + 1) / 2) * width, ((1 - y) / 2) * height, dot, dot);
    }
    ctx.globalCompositeOperation = "source-over";
  }
}
