/**
 * EZO's energy presence. Raw WebGL is the portable equivalent of a Three.js
 * point/shader scene: no character mesh, model file, skin or facial features.
 * The public API is shared by web, Electron and Capacitor.
 */
import { buildEnergyFigure, type EnergyFigure } from "./energy-figure";
import { ENERGY_FRAGMENT, ENERGY_VERTEX } from "./energy-shaders";
import { followLevel } from "./level";
import { frameCamera, project, type Framing } from "./math";
import { easeLook, lookFor, TRANSIENT_STATES, type AvatarState, type Look } from "./states";

export type QualityProfile = "auto" | "high" | "balanced" | "low";
export type AudioChannel = "microphone" | "output";
export interface Gaze { yaw: number; pitch: number }
export interface AvatarOptions {
  framing?: Framing;
  /** @deprecated Legacy styles now resolve to the same non-character energy figure. */
  style?: "energy" | "expressive" | "holographic";
  quality?: QualityProfile;
  terrain?: boolean;
  reducedMotion?: boolean;
  intensity?: number;
  describe?: (state: AvatarState) => string;
  power?: "auto" | "low" | "high";
}
interface GlState {
  gl: WebGLRenderingContext;
  points: WebGLProgram;
  mask: WebGLProgram;
  buffers: WebGLBuffer[];
  uniforms: Record<string, WebGLUniformLocation | null>;
  maskUniforms: Record<string, WebGLUniformLocation | null>;
  attributes: number[];
  xy: number;
}
const PARAMETERS = ["uTime", "uLevel", "uEnergy", "uWarmth", "uListen", "uThink", "uSpeak", "uError", "uWork", "uSuccess", "uOffline", "uYaw", "uPitch", "uPx", "uGlowPx", "uRef", "uGlow", "uIntensity"] as const;
const MASK_VERTEX = `attribute vec2 aXY; uniform mat4 uVP; uniform float uYaw,uPitch;
void main(){vec3 p=vec3(aXY,0.0);p.y-=0.12;float c=cos(uYaw),s=sin(uYaw);p=vec3(c*p.x+s*p.z,p.y,-s*p.x+c*p.z);c=cos(uPitch);s=sin(uPitch);p=vec3(p.x,c*p.y-s*p.z,s*p.y+c*p.z);p.y+=0.12;gl_Position=uVP*vec4(p,1.0);}`;
const MASK_FRAGMENT = `precision mediump float; void main(){gl_FragColor=vec4(0.0);}`;
const clamp1 = (v: number) => Math.min(1, Math.max(0, Number.isFinite(v) ? v : 0));

function compile(gl: WebGLRenderingContext, vertex: string, fragment: string) {
  const program = gl.createProgram();
  if (!program) throw new Error("Shader allocation failed");
  const shaders: WebGLShader[] = [];
  try {
    for (const [type, source] of [[gl.VERTEX_SHADER, vertex], [gl.FRAGMENT_SHADER, fragment]] as const) {
      const shader = gl.createShader(type);
      if (!shader) throw new Error("Shader allocation failed");
      shaders.push(shader);
      gl.shaderSource(shader, source); gl.compileShader(shader);
      if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(shader) ?? "Shader compilation failed");
      gl.attachShader(program, shader);
    }
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(program) ?? "Shader link failed");
    return program;
  } catch (error) { gl.deleteProgram(program); throw error; }
  finally { shaders.forEach((shader) => gl.deleteShader(shader)); }
}

export class EzoAvatar {
  readonly canvas: HTMLCanvasElement;
  readonly framing: Framing;
  readonly renderer: "webgl" | "2d" | "none";
  private figure: EnergyFigure;
  private glState: GlState | null = null;
  private state: AvatarState = "idle";
  private look: Look = { ...lookFor("idle") };
  private quality: QualityProfile;
  private resolvedQuality: "high" | "low";
  private density = 1;
  private readonly terrain: boolean;
  private lowPower: boolean;
  private reduced: boolean;
  private motionOverride: boolean | undefined;
  private intensity = 1;
  private active = true;
  private running = false;
  private destroyed = false;
  private frame = 0;
  private frames = 0;
  private last = 0;
  private time = 0;
  private stateAt = 0;
  private frameMs = 0;
  private drawMs = 0;
  private measured = 0;
  private glow = false;
  private glowLost = false;
  private level = 0;
  private levelTarget = 0;
  private levelAt = -Infinity;
  private channel: AudioChannel = "output";
  private gaze: Gaze = { yaw: 0, pitch: 0 };
  private gazeTarget: Gaze = { yaw: 0, pitch: 0 };
  private gazeAt = -Infinity;
  private describe: AvatarOptions["describe"];
  private readonly observer: ResizeObserver | null;
  private readonly media = typeof window !== "undefined" ? window.matchMedia?.("(prefers-reduced-motion: reduce)") : null;
  private readonly onMotion = () => { if (this.motionOverride === undefined) this.setReducedMotion(this.media?.matches ?? false); };
  private readonly onVisibility = () => this.syncRunning();
  private readonly onLost = (event: Event) => {
    event.preventDefault(); this.glState = null; this.stopLoop();
    this.canvas.dataset.ezoAvatar = "context-lost";
  };
  private readonly onRestored = () => {
    this.glState = this.initGl();
    this.canvas.dataset.ezoAvatar = this.glState ? "webgl" : "context-lost";
    this.syncRunning();
  };

  constructor(canvas: HTMLCanvasElement, options: AvatarOptions = {}) {
    this.canvas = canvas;
    this.framing = options.framing ?? "bust";
    this.terrain = options.terrain ?? this.framing === "bust";
    this.quality = options.quality ?? "auto";
    this.motionOverride = options.reducedMotion;
    this.reduced = options.reducedMotion ?? this.media?.matches ?? false;
    this.intensity = options.intensity ?? 1;
    this.describe = options.describe;
    const rect = canvas.getBoundingClientRect();
    const small = rect.width > 0 && rect.height > 0 && Math.max(rect.width, rect.height) < 260;
    const dense = typeof window !== "undefined" && window.devicePixelRatio > 2.5;
    this.resolvedQuality = this.quality === "high" || (this.quality === "auto" && !small && !dense && !EzoAvatar.prefersLowPower()) ? "high" : "low";
    this.lowPower = options.power === "low" || (options.power !== "high" && EzoAvatar.prefersLowPower()) || this.quality === "low";
    const started = typeof performance !== "undefined" ? performance.now() : 0;
    this.figure = buildEnergyFigure(this.resolvedQuality, this.terrain);
    const buildMs = typeof performance !== "undefined" ? performance.now() - started : 0;
    this.glState = this.initGl();
    this.renderer = this.glState ? "webgl" : canvas.getContext("2d") ? "2d" : "none";
    Object.assign(canvas.dataset, { ezoAvatar: this.renderer, style: "energy", quality: this.resolvedQuality, profile: this.quality, points: String(this.figure.count), buildMs: buildMs.toFixed(1), power: this.lowPower ? "low" : "high", glow: "off", motion: this.reduced ? "reduced" : "full", state: this.state });
    this.setIntensity(this.intensity);
    this.label();
    canvas.addEventListener("webglcontextlost", this.onLost);
    canvas.addEventListener("webglcontextrestored", this.onRestored);
    if (typeof document !== "undefined") document.addEventListener("visibilitychange", this.onVisibility);
    this.media?.addEventListener?.("change", this.onMotion);
    this.observer = typeof ResizeObserver !== "undefined" ? new ResizeObserver(() => this.redrawIfStill()) : null;
    this.observer?.observe(canvas);
    this.syncRunning();
  }

  static supported(): boolean {
    if (typeof document === "undefined") return false;
    try {
      const canvas = document.createElement("canvas");
      const gl = canvas.getContext("webgl");
      const supported = Boolean(gl);
      gl?.getExtension("WEBGL_lose_context")?.loseContext();
      return supported;
    } catch { return false; }
  }
  static prefersLowPower(): boolean {
    if (typeof navigator === "undefined") return false;
    const nav = navigator as Navigator & { deviceMemory?: number; connection?: { saveData?: boolean } };
    return (nav.deviceMemory !== undefined && nav.deviceMemory <= 4) || Boolean(nav.connection?.saveData) || (nav.hardwareConcurrency > 0 && nav.hardwareConcurrency <= 2);
  }
  setLowPower(on: boolean) { this.lowPower = on; this.canvas.dataset.power = on ? "low" : "high"; if (on) { this.glow = false; this.canvas.dataset.glow = "off"; } }
  isLowPower() { return this.lowPower; }
  setActive(active: boolean) { this.active = active; this.syncRunning(); }
  getFrameCount() { return this.frames; }
  getPerformance() {
    const heap = (performance as unknown as { memory?: { usedJSHeapSize?: number } }).memory?.usedJSHeapSize;
    return { frameMs: +this.frameMs.toFixed(2), drawMs: +this.drawMs.toFixed(2), fps: this.frameMs ? +(1000 / this.frameMs).toFixed(1) : 0, heapMb: typeof heap === "number" ? +(heap / 1048576).toFixed(1) : null };
  }
  getQuality() { return { profile: this.quality, resolved: this.resolvedQuality, points: this.drawCount(), density: this.density }; }
  setQuality(profile: QualityProfile) {
    if (profile === this.quality) return;
    this.quality = profile;
    const next = profile === "high" || (profile === "auto" && !EzoAvatar.prefersLowPower() && this.framing === "bust") ? "high" : "low";
    this.density = 1; this.measured = 0; this.glowLost = false;
    if (next !== this.resolvedQuality) {
      this.resolvedQuality = next;
      this.figure = buildEnergyFigure(next, this.terrain);
      if (this.glState) {
        this.glState.buffers.forEach((buffer) => this.glState!.gl.deleteBuffer(buffer));
        this.glState.buffers = this.uploadBuffers(this.glState.gl);
      }
    }
    this.setLowPower(profile === "low" || EzoAvatar.prefersLowPower());
    Object.assign(this.canvas.dataset, { profile, quality: next, points: String(this.figure.count) });
    this.redrawIfStill();
  }
  setReducedMotion(reduced: boolean) {
    this.reduced = reduced;
    this.canvas.dataset.motion = reduced ? "reduced" : "full";
    this.syncRunning();
  }
  setMotionPreference(preference: "system" | "reduced") {
    this.motionOverride = preference === "reduced" ? true : undefined;
    this.setReducedMotion(this.motionOverride ?? this.media?.matches ?? false);
  }
  setIntensity(value: number) { this.intensity = 0.35 + clamp1(value) * 0.65; this.canvas.dataset.intensity = this.intensity.toFixed(2); this.redrawIfStill(); }
  setState(state: AvatarState) {
    if (state === this.state) return;
    this.state = state; this.stateAt = this.time;
    this.canvas.dataset.state = state;
    this.level = 0; this.levelTarget = 0; this.levelAt = -Infinity;
    this.label();
    if (this.reduced || !this.running) { this.look = { ...lookFor(state) }; this.redrawIfStill(); }
  }
  getState() { return this.state; }
  getLevel() { return this.level; }
  hasLiveLevel() { return this.time - this.levelAt < 0.3 && this.channel === (this.state === "listening" ? "microphone" : "output") && (this.state === "listening" || this.state === "speaking"); }
  /** Only real PCM measurements enter here. Stale/unavailable audio settles to zero; no synthetic speech. */
  setLevel(level: number, channel: AudioChannel = "output") {
    const expected = this.state === "listening" ? "microphone" : "output";
    if (channel !== expected || (this.state !== "listening" && this.state !== "speaking")) return;
    this.levelTarget = clamp1(level); this.levelAt = this.time; this.channel = channel;
    if (this.reduced) { this.level = this.levelTarget; this.redrawIfStill(); }
  }
  setGaze(gaze: Gaze | null) {
    if (!gaze) { this.gazeAt = -Infinity; return; }
    const clamp = (v: number) => Math.max(-1, Math.min(1, Number.isFinite(v) ? v : 0));
    this.gazeTarget = { yaw: clamp(gaze.yaw), pitch: clamp(gaze.pitch) }; this.gazeAt = this.time;
    if (this.reduced) this.redrawIfStill();
  }
  destroy() {
    this.destroyed = true; this.stopLoop(); this.observer?.disconnect();
    this.canvas.removeEventListener("webglcontextlost", this.onLost);
    this.canvas.removeEventListener("webglcontextrestored", this.onRestored);
    if (typeof document !== "undefined") document.removeEventListener("visibilitychange", this.onVisibility);
    this.media?.removeEventListener?.("change", this.onMotion);
    this.releaseBuffers(); this.glState = null;
  }
  private label() { if (this.describe) { this.canvas.setAttribute("role", "img"); this.canvas.setAttribute("aria-label", this.describe(this.state)); } }
  private drawCount() { return Math.max(1, Math.floor(this.figure.count * this.density)); }
  private uploadBuffers(gl: WebGLRenderingContext) {
    const buffers: WebGLBuffer[] = [];
    try {
      for (const data of [this.figure.positions, this.figure.data, this.figure.extra, this.figure.silhouette]) {
        const buffer = gl.createBuffer(); if (!buffer) throw new Error("Buffer allocation failed");
        buffers.push(buffer); gl.bindBuffer(gl.ARRAY_BUFFER, buffer); gl.bufferData(gl.ARRAY_BUFFER, data, gl.STATIC_DRAW);
      }
      return buffers;
    } catch (error) { buffers.forEach((buffer) => gl.deleteBuffer(buffer)); throw error; }
  }
  private releaseBuffers() {
    const state = this.glState; if (!state) return;
    state.buffers.forEach((buffer) => state.gl.deleteBuffer(buffer));
    state.gl.deleteProgram(state.points); state.gl.deleteProgram(state.mask); state.buffers = [];
  }
  private initGl(): GlState | null {
    let gl: WebGLRenderingContext | null = null;
    try { gl = this.canvas.getContext("webgl", { alpha: true, antialias: false, premultipliedAlpha: true, depth: true, powerPreference: "low-power" }); } catch { return null; }
    if (!gl) return null;
    try {
      const points = compile(gl, ENERGY_VERTEX, ENERGY_FRAGMENT);
      const mask = compile(gl, MASK_VERTEX, MASK_FRAGMENT);
      return { gl, points, mask, buffers: this.uploadBuffers(gl), uniforms: Object.fromEntries(["uVP", ...PARAMETERS].map((name) => [name, gl.getUniformLocation(points, name)])), maskUniforms: Object.fromEntries(["uVP", "uYaw", "uPitch"].map((name) => [name, gl.getUniformLocation(mask, name)])), attributes: ["aPos", "aData", "aExtra"].map((name) => gl.getAttribLocation(points, name)), xy: gl.getAttribLocation(mask, "aXY") };
    } catch (error) { console.warn("EZO energy: GPU initialization failed.", error); return null; }
  }
  private syncRunning() {
    const visible = typeof document === "undefined" || document.visibilityState !== "hidden";
    if (!this.destroyed && !this.reduced && this.glState && visible && this.active) this.startLoop();
    else { this.stopLoop(); this.redrawIfStill(); }
  }
  private startLoop() {
    if (this.running) return;
    this.running = true; this.last = performance.now();
    const tick = (now: number) => {
      if (!this.running) return;
      this.frame = requestAnimationFrame(tick);
      const cap = this.lowPower || this.quality === "low" ? 1000 / 30 : this.quality === "balanced" ? 1000 / 45 : 0;
      if (cap && now - this.last < cap - 1) return;
      const interval = now - this.last;
      const dt = Math.min(0.1, Math.max(0, interval / 1000)); this.last = now;
      const started = performance.now(); this.step(dt); this.draw();
      const cost = performance.now() - started;
      this.frameMs = this.frameMs ? this.frameMs * 0.94 + interval * 0.06 : interval;
      this.drawMs = this.drawMs ? this.drawMs * 0.94 + cost * 0.06 : cost;
      this.measured++;
      if (this.measured >= 60 && this.quality === "auto") {
        if (this.frameMs > 29 && this.density > 0.4) { this.density = Math.max(0.4, this.density - 0.2); this.glow = false; this.glowLost = true; this.measured = 0; }
        else if (this.frameMs < 19 && this.density < 1) { this.density = Math.min(1, this.density + 0.1); this.measured = 0; }
      }
      if (!this.glow && !this.glowLost && !this.lowPower && this.measured >= 60 && this.frameMs < 20) { this.glow = true; this.canvas.dataset.glow = "on"; }
      else if (this.glow && this.frameMs > 27) { this.glow = false; this.glowLost = true; this.canvas.dataset.glow = "off"; }
      this.canvas.dataset.drawnPoints = String(this.drawCount());
    };
    this.frame = requestAnimationFrame(tick);
  }
  private stopLoop() { this.running = false; if (this.frame) cancelAnimationFrame(this.frame); this.frame = 0; }
  private step(dt: number) {
    this.time += dt;
    const hold = TRANSIENT_STATES[this.state]; if (hold !== undefined && this.time - this.stateAt > hold) this.setState("idle");
    this.look = easeLook(this.look, lookFor(this.state), dt);
    const held = this.time - this.gazeAt < 0.45;
    const target = held ? this.gazeTarget : { yaw: 0, pitch: 0 };
    const k = 1 - Math.exp(-dt * (held ? 7 : 2));
    this.gaze.yaw += (target.yaw - this.gaze.yaw) * k; this.gaze.pitch += (target.pitch - this.gaze.pitch) * k;
    this.level = followLevel(this.level, this.hasLiveLevel() ? this.levelTarget : 0, dt);
  }
  private redrawIfStill() {
    if (this.running || this.destroyed) return;
    if (this.reduced) { this.time = 6.5; this.look = { ...lookFor(this.state) }; if (!this.hasLiveLevel()) this.level = 0; }
    this.draw();
  }
  private resize() {
    const rect = this.canvas.getBoundingClientRect();
    const cap = this.quality === "low" ? 1 : this.quality === "balanced" ? 1.5 : 2;
    const dpr = Math.min(typeof window !== "undefined" ? window.devicePixelRatio || 1 : 1, cap);
    const width = Math.max(1, Math.round((rect.width || this.canvas.width) * dpr));
    const height = Math.max(1, Math.round((rect.height || this.canvas.height) * dpr));
    if (this.canvas.width !== width || this.canvas.height !== height) { this.canvas.width = width; this.canvas.height = height; }
    return { width, height, cssHeight: height / dpr, dpr };
  }
  private motion() {
    const t = this.reduced ? 0 : this.time;
    return { yaw: 0.055 * Math.sin(t * 0.23) + 0.025 * Math.sin(t * 0.47) + this.gaze.yaw * 0.24, pitch: 0.018 * Math.sin(t * 0.19) + this.gaze.pitch * 0.14 };
  }
  private draw() {
    if (this.destroyed) return;
    this.frames++;
    const { width, height, cssHeight, dpr } = this.resize();
    const camera = frameCamera(this.framing, width / height);
    if (!this.glState) { this.drawStill(camera.viewProjection, width, height); return; }
    const { gl, points, mask, buffers, uniforms, maskUniforms, attributes, xy } = this.glState;
    const { yaw, pitch } = this.motion();
    gl.viewport(0, 0, width, height); gl.clearColor(0, 0, 0, 0); gl.clearDepth(1); gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
    gl.enable(gl.DEPTH_TEST); gl.depthFunc(gl.LESS); gl.useProgram(mask); gl.colorMask(false, false, false, false); gl.depthMask(true); gl.disable(gl.BLEND);
    gl.uniformMatrix4fv(maskUniforms.uVP!, false, camera.viewProjection); gl.uniform1f(maskUniforms.uYaw!, yaw); gl.uniform1f(maskUniforms.uPitch!, pitch);
    gl.bindBuffer(gl.ARRAY_BUFFER, buffers[3]!); gl.enableVertexAttribArray(xy); gl.vertexAttribPointer(xy, 2, gl.FLOAT, false, 0, 0);
    gl.drawArrays(gl.TRIANGLES, 0, this.figure.silhouette.length / 2); gl.disableVertexAttribArray(xy);
    gl.useProgram(points); gl.colorMask(true, true, true, true); gl.depthMask(false); gl.enable(gl.BLEND); gl.blendFunc(gl.ONE, gl.ONE);
    gl.uniformMatrix4fv(uniforms.uVP!, false, camera.viewProjection);
    const values: Record<string, number> = { uTime: this.time, uLevel: this.level, uEnergy: this.look.energy, uWarmth: this.look.warmth, uListen: this.look.listen, uThink: this.look.think, uSpeak: this.look.speak, uError: this.look.error, uWork: this.look.work, uSuccess: this.look.success, uOffline: this.look.offline, uYaw: yaw, uPitch: pitch, uIntensity: this.intensity };
    for (const name of PARAMETERS) gl.uniform1f(uniforms[name]!, values[name] ?? 0);
    const reference = this.framing === "head" ? 380 : 720;
    gl.uniform1f(uniforms.uPx!, dpr * Math.min(1.5, Math.max(0.6, cssHeight / reference)));
    gl.uniform1f(uniforms.uGlowPx!, dpr * Math.min(1.5, Math.max(0.1, cssHeight / reference)));
    gl.uniform1f(uniforms.uRef!, camera.distance);
    [3, 4, 2].forEach((size, index) => { const location = attributes[index]!; gl.bindBuffer(gl.ARRAY_BUFFER, buffers[index]!); gl.enableVertexAttribArray(location); gl.vertexAttribPointer(location, size, gl.FLOAT, false, 0, 0); });
    if (this.glow && !this.lowPower) { gl.uniform1f(uniforms.uGlow!, 1); gl.drawArrays(gl.POINTS, 0, this.drawCount()); }
    gl.uniform1f(uniforms.uGlow!, 0); gl.drawArrays(gl.POINTS, 0, this.drawCount());
    attributes.forEach((location) => gl.disableVertexAttribArray(location));
  }
  /** Graceful fallback is the SAME contour anatomy, not a robot, orb or stock avatar. */
  private drawStill(vp: Float32Array, width: number, height: number) {
    const ctx = this.canvas.getContext("2d"); if (!ctx) return;
    ctx.clearRect(0, 0, width, height); ctx.globalCompositeOperation = "lighter";
    const { yaw, pitch } = this.motion(); const cy = Math.cos(yaw), sy = Math.sin(yaw), cp = Math.cos(pitch), sp = Math.sin(pitch);
    const stride = Math.max(1, Math.ceil(this.figure.count / 14000));
    for (let i = 0; i < this.figure.count; i += stride) {
      const kind = this.figure.data[i * 4]!, warm = this.figure.data[i * 4 + 3]!;
      if (kind === 3 || kind === 5 || kind === 6) continue;
      const x = this.figure.positions[i * 3]!, y0 = this.figure.positions[i * 3 + 1]! - 0.12, z = this.figure.positions[i * 3 + 2]!;
      const rx = cy * x + sy * z, rz = -sy * x + cy * z;
      const [nx, ny] = project(vp, rx, cp * y0 - sp * rz + 0.12, sp * y0 + cp * rz);
      const color = this.state === "offline" ? "100,140,150" : warm > 0.35 && kind < 1 ? "255,155,55" : "65,210,255";
      ctx.fillStyle = `rgba(${color},${(0.3 + this.figure.data[i * 4 + 2]! * 0.4) * this.intensity})`;
      const dot = Math.max(1, height / 600); ctx.fillRect((nx + 1) * width / 2, (1 - ny) * height / 2, dot, dot);
    }
    ctx.globalCompositeOperation = "source-over";
  }
}
