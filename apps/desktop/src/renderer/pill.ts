// The floating pill: idle → listening → recognizing → thinking/working → speaking, always
// with a visible state and a real stop. Audio is recorded only while the red listening
// state is shown. Every word comes from the main process in the owner's language.
import { createLevelMeter, createVoiceFrame, EzoAvatar, MotionAdapter, type AttentionView, type AvatarState, type LevelMeter, type VisionStatus, type VoiceFrame } from "@ezo/avatar";
import type { MicrophoneStatus } from "@ezo/face-tracking";
import { AcknowledgementSpeaker, acknowledgement, loadVisionAssets, PerceptionSession, VoiceReaction, type AssetsReadiness, type Diagnostics } from "@ezo/perception-client";

interface TurnResponse {
  transcript?: string;
  reply?: string;
  acted?: boolean;
  audio?: { mimeType: string; data: Uint8Array };
  error?: string;
  notice?: string;
  cancelled?: boolean;
}

type PillStrings = Record<string, string>;
interface PillInit {
  strings: PillStrings;
  shortcut: string;
  language: string;
  status: PillStatus;
  media?: { microphone: boolean; camera: boolean };
  lowPower?: boolean;
  voiceVolume?: number;
  clap?: { listening: boolean; startsListening: boolean };
  build?: { version: string; sha: string };
}
interface PillStatus {
  online: boolean;
  ai: boolean;
  voice: boolean;
  text: string;
}
interface TaskSummary {
  id: string;
  state: string;
  step: string | null;
  waiting: boolean;
  report: string;
}
interface History {
  ok: boolean;
  conversationId?: string | null;
  messages?: { role: string; content: string }[];
  message?: string;
}

interface EzoBridge {
  init(): Promise<PillInit>;
  sendAudio(audio: ArrayBuffer, mimeType: string): Promise<TurnResponse>;
  sendText(text: string): Promise<TurnResponse>;
  cancelTurn(): void;
  openSettings(): void;
  setFocusable(focusable: boolean): void;
  setHeight(height: number): void;
  setExpanded(expanded: boolean): void;
  refreshStatus(): Promise<PillStatus>;
  recentHistory(): Promise<History>;
  conversations(): Promise<{ ok: boolean; conversations?: { id: string; title: string }[]; message?: string }>;
  switchConversation(id: string | null): Promise<string | null>;
  tasks(): Promise<TaskSummary[]>;
  cancelTask(id: string): Promise<{ ok: boolean }>;
  speak?(text: string, language: string): Promise<{ mimeType?: string; data?: Uint8Array; provider?: string | null; error?: string }>;
  reportDiagnostics?(diagnostics: unknown): void;
  onToggle(callback: () => void): void;
  onNotice(callback: (text: unknown) => void): void;
  onError(callback: (text: unknown) => void): void;
  onStage(callback: (stage: unknown) => void): void;
  onStatus(callback: (status: unknown) => void): void;
  onTasks(callback: (tasks: unknown) => void): void;
  onInit(callback: (init: unknown) => void): void;
  onVisibility?(callback: (visible: unknown) => void): void;
  onExpanded?(callback: (expanded: unknown) => void): void;
}

const ezo = (window as unknown as { ezo: EzoBridge }).ezo;
type State = AvatarState;

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
const pill = $("pill");
const label = $("label");
const hint = $("hint");
const panel = $("panel");
const stage = $("stage");
const dot = $("dot");
const mediaBox = $("media");
const stopButton = $<HTMLButtonElement>("stop");
const question = $<HTMLInputElement>("question");

const MAX_RECORDING_MS = 30_000;
const BUSY: ReadonlySet<State> = new Set(["recognizing", "thinking", "working"]);
let t: PillStrings = {};
let shortcut = "Ctrl+Alt+Space";
let state: State = "idle";
let status: PillStatus = { online: true, ai: true, voice: true, text: "" };
let recorder: MediaRecorder | null = null;
let stream: MediaStream | null = null;
let chunks: Blob[] = [];
let cancelled = false;
let player: HTMLAudioElement | null = null;
let recordingTimer: number | undefined;
let turnId = 0;
let settleTimer: number | undefined;
const SUCCESS_MS = 1600; // the figure's own gold burst lasts this long
let media: { microphone: boolean; camera: boolean } = { microphone: true, camera: false };
let lowPower = false;
let voiceVolume = 1;
let clapSettings = { listening: false, startsListening: false };
let expanded = false;
let visible = true;

// EZO's humanoid face follows the microphone while listening and its own voice while speaking.
// One figure at a time: the small head in the pill, or the bust on the expanded stage.
let face: EzoAvatar | null = null;
let frame: VoiceFrame | null = null;
const webgl = EzoAvatar.supported();
if (webgl) document.body.classList.add("has-face");

function mountFace(): void {
  unmountPerception(); // camera, clap microphone and the worker never outlive the figure
  frame?.destroy();
  frame = null;
  face?.destroy();
  face = null;
  if (!webgl) return;
  const canvas = expanded ? $<HTMLCanvasElement>("stageFace") : $<HTMLCanvasElement>("face");
  face = new EzoAvatar(canvas, {
    framing: expanded ? "bust" : "head",
    quality: expanded ? "auto" : "low",
    terrain: expanded,
    power: lowPower ? "low" : "auto",
    describe: (s) => t[s] ?? s,
  });
  face.setState(state);
  face.setActive(visible);
  if (expanded) {
    frame = createVoiceFrame($("stageFrame"), { words: {}, showWord: false });
    frame.follow(face);
    mountPerception();
  }
}

// Perception on the stage: the real engine (@ezo/face-tracking in a worker; assets bundled
// under /vision on the app origin and SHA256-verified) feeds the figure through MotionAdapter.
// The clap microphone is a separate consent (settings + the Listen button). Nothing is
// recorded or uploaded; a clap never runs a command.
const VISION_BASE = "/vision/";
let adapter: MotionAdapter | null = null;
let perception: PerceptionSession | null = null;
let readiness: AssetsReadiness | null = null;
let vision: VisionStatus = { camera: "off", since: 0 };
let microphone: { status: MicrophoneStatus; error?: string } = { status: "off" };
let diagnostics: Diagnostics | null = null;
let lastTts: { provider: string | null; latencyMs: number; cached: boolean; at: number } | null = null;
let acknowledging = false;
const speaker = new AcknowledgementSpeaker({
  synthesize: async (text, language) => {
    const result = await ezo.speak?.(text, language);
    if (!result || result.error || !result.data) throw new Error(result?.error ?? "voice unavailable");
    return { audio: new Blob([result.data.slice()], { type: result.mimeType ?? "audio/mpeg" }), provider: result.provider ?? null };
  },
  cacheKey: () => `${status.voice ? "voice" : "novoice"}|${status.text}`,
  volume: () => voiceVolume,
  onLevel: (level) => face?.setLevel(level),
  onSynthesized: (info) => {
    lastTts = { ...info, at: Date.now() };
    reportDiagnostics();
  },
});
const reaction = new VoiceReaction(speaker, (event) => {
  if (event.type === "start") {
    acknowledging = true;
    stopSpeaking();
    perception?.setInteraction("speaking");
    setState("speaking");
  } else if (event.type === "unavailable" || event.type === "error") {
    // Not spoken: no provider, or it failed. Never a pretended playback.
    setState("idle", fmt("clapUnavailable"));
  } else if (event.type === "end" && acknowledging) {
    acknowledging = false;
    perception?.setInteraction(null);
    if (clapSettings.startsListening && media.microphone && state === "speaking") void startListening();
    else if (state === "speaking") setState("idle");
  }
});

function renderAttention(view: AttentionView): void {
  $("attention").textContent =
    view.source === "hand" ? fmt("attentionHand") : view.source === "face" ? fmt("attentionHead") : view.source === "pointer" || view.source === "touch" ? fmt("attentionPointer") : "";
}

function renderMedia(): void {
  const chips: HTMLElement[] = [];
  if (stream || microphone.status === "active") {
    const mic = document.createElement("span");
    mic.textContent = "MIC";
    mic.title = stream ? fmt("micActive") : fmt("clapActive");
    mic.setAttribute("aria-label", mic.title);
    chips.push(mic);
  }
  if (vision.camera === "tracking" || vision.camera === "lost" || vision.camera === "requesting") {
    const cam = document.createElement("span");
    cam.className = "cam";
    cam.textContent = "CAM";
    cam.title = fmt("cameraActive");
    cam.setAttribute("aria-label", fmt("cameraActive"));
    chips.push(cam);
  }
  mediaBox.replaceChildren(...chips);
}

function renderCamera(): void {
  const stateBox = $("cameraState");
  const button = $<HTMLButtonElement>("cameraToggle");
  stateBox.dataset.camera = vision.camera;
  const words: Record<string, string> = {
    off: fmt("cameraOff"),
    requesting: fmt("cameraRequesting"),
    denied: fmt("cameraDenied"),
    unavailable: fmt("cameraUnavailable"),
    tracking: fmt("cameraTracking"),
    lost: fmt("cameraLost"),
    error: fmt("cameraError", { detail: vision.message ?? "" }),
  };
  stateBox.textContent = (words[vision.camera] ?? vision.camera) + (vision.simulated ? ` (${fmt("attentionSimulated")})` : "");
  const ready = Boolean(readiness?.ready);
  const running = vision.camera !== "off";
  button.disabled = !ready || !media.camera;
  button.textContent = running ? fmt("cameraStop") : fmt("cameraOn");
  const reason = !media.camera
    ? fmt("cameraSettings")
    : !readiness
      ? ""
      : readiness.ready
        ? ""
        : readiness.reason === "missing"
          ? fmt("cameraAssetsMissing")
          : readiness.reason === "invalid"
            ? fmt("cameraAssetsInvalid", { detail: readiness.detail })
            : fmt("cameraError", { detail: readiness.detail });
  button.title = reason;
  $("cameraPrivacy").textContent = reason || `${fmt("cameraPrivacy")} ${fmt("cameraEngine")}`;
  // Clap row.
  const clapBox = $("clapState");
  const clapButton = $<HTMLButtonElement>("clapToggle");
  clapBox.dataset.microphone = microphone.status;
  const micWords: Record<MicrophoneStatus, string> = {
    off: fmt("clapOff"),
    requesting: fmt("clapRequesting"),
    active: fmt("clapActive"),
    error: /denied|NotAllowed|permission/i.test(microphone.error ?? "") ? fmt("clapDenied") : fmt("clapError", { detail: microphone.error ?? "" }),
  };
  clapBox.textContent = micWords[microphone.status];
  const micRunning = microphone.status === "active" || microphone.status === "requesting";
  clapButton.disabled = !ready || !clapSettings.listening || !media.microphone;
  clapButton.textContent = micRunning ? fmt("clapStop") : fmt("clapListen");
  clapButton.title = !clapSettings.listening ? fmt("clapSettings") : !media.microphone ? fmt("micOff") : "";
  $("clapHeard").textContent = diagnostics?.clapCount ? `${fmt("clap")} ×${diagnostics.clapCount}` : "";
  $("clapPrivacy").textContent = !clapSettings.listening ? fmt("clapSettings") : fmt("clapPrivacy");
  stage.dataset.fps = String(diagnostics?.cameraFps ?? 0);
  stage.dataset.inferenceMs = String(diagnostics?.inferenceMs ?? "");
  stage.dataset.attention = diagnostics?.attention ?? "neutral";
  stage.dataset.clapCount = String(diagnostics?.clapCount ?? 0);
  renderMedia();
}

let diagnosticsTimer: number | undefined;
/** The Diagnostics numbers go to the main process (settings window shows them); at most once a second. */
function reportDiagnostics(): void {
  if (diagnosticsTimer !== undefined) return;
  diagnosticsTimer = window.setTimeout(() => {
    diagnosticsTimer = undefined;
    ezo.reportDiagnostics?.({
      ...(diagnostics ?? {}),
      camera: vision.camera,
      microphone: microphone.status,
      stage: expanded ? "expanded" : "pill",
      figure: face
        ? { renderer: face.renderer, points: face.canvas.dataset.points, power: face.canvas.dataset.power, frames: face.getFrameCount(), level: Number(face.getLevel().toFixed(2)), liveLevel: face.hasLiveLevel() }
        : null,
      vision: readiness ? (readiness.ready ? "assets verified" : `${readiness.reason}: ${readiness.detail}`) : "checking",
      tts: lastTts,
    });
  }, 1000);
}

async function startCamera(): Promise<void> {
  if (!media.camera) return;
  await perception?.startCamera();
  renderCamera();
}

function stopCamera(): void {
  perception?.stopCamera();
  renderCamera();
}

async function toggleClap(): Promise<void> {
  if (microphone.status === "active" || microphone.status === "requesting") {
    perception?.stopClap();
    return;
  }
  if (!clapSettings.listening || !media.microphone) return;
  await perception?.startClap();
  renderCamera();
}

/** Mounts the engine for the expanded stage; one session per figure, released with it. */
function mountPerception(): void {
  if (!face || !readiness?.ready || perception) return;
  adapter = new MotionAdapter(face, { onChange: renderAttention });
  perception = new PerceptionSession({
    base: VISION_BASE,
    assets: readiness.assets,
    video: $<HTMLVideoElement>("perceptionVideo"),
    cameraIndicator: $("cameraIndicator"),
    microphoneIndicator: $("microphoneIndicator"),
    adapter,
    lowPower,
    reducedMotion: matchMedia("(prefers-reduced-motion: reduce)").matches,
    onVision: (next) => {
      vision = next;
      renderCamera();
      reportDiagnostics();
    },
    onMicrophone: (next, error) => {
      microphone = { status: next, error };
      renderCamera();
      reportDiagnostics();
    },
    onDiagnostics: (next) => {
      diagnostics = next;
      renderCamera();
      reportDiagnostics();
    },
    onClap: (event) => {
      // Acknowledgement only, in the app language: never a send, a tool or listening by itself.
      try {
        void reaction.react(acknowledgement(event, (document.documentElement.lang as "uz" | "en" | "ru") || "uz"));
      } catch {
        // below the engine's confidence floor
      }
    },
  });
  adapter.setVisible(visible);
}

function unmountPerception(): void {
  reaction.stop();
  speaker.stop();
  perception?.stop();
  perception = null;
  adapter?.stop();
  adapter = null;
  vision = { camera: "off", since: performance.now() };
  microphone = { status: "off" };
  diagnostics = null;
  acknowledging = false;
}

function setExpanded(next: boolean): void {
  if (expanded === next) return;
  expanded = next;
  stage.hidden = !next;
  $("expand").setAttribute("aria-pressed", String(next));
  $("expand").textContent = next ? "⤡" : "⤢";
  mountFace(); // unmounts the previous figure, its camera, microphone and worker
  renderCamera();
  resize();
}

let meter: LevelMeter | null = null;
let meterFrame = 0;

function followLevel(source: MediaStream | HTMLMediaElement | null): void {
  cancelAnimationFrame(meterFrame);
  meter?.close();
  meter = face && source ? createLevelMeter(source) : null;
  const tick = () => {
    if (!meter) return;
    face?.setLevel(meter.read());
    meterFrame = requestAnimationFrame(tick);
  };
  if (meter) meterFrame = requestAnimationFrame(tick);
}

function fmt(key: string, values: Record<string, string> = {}): string {
  return (t[key] ?? key).replace(/\{(\w+)\}/g, (match, name: string) => values[name] ?? match);
}

function resize(): void {
  requestAnimationFrame(() => ezo.setHeight(panel.hidden && stage.hidden ? 72 : document.body.scrollHeight + 4));
}

function setState(next: State, detail?: string): void {
  state = next;
  pill.className = `pill ${next}`;
  face?.setState(next);
  window.clearTimeout(settleTimer);
  if (next === "success") settleTimer = window.setTimeout(() => state === "success" && setState("idle"), SUCCESS_MS);
  label.textContent = next === "idle" && !status.online ? fmt("offline") : fmt(next);
  hint.textContent = detail ?? (next === "idle" ? (status.online ? fmt("idleHint", { shortcut }) : fmt("offlineHint")) : fmt(`${next}Hint`));
  stopButton.hidden = next === "idle" || next === "error" || next === "success" || next === "offline";
}

function showPanel(transcript: string, reply: string): void {
  panel.hidden = false;
  $("transcript").textContent = transcript ? `${fmt("you")}: ${transcript}` : "";
  $("reply").textContent = reply;
  resize();
}

function hidePanelIfEmpty(): void {
  if (!$("reply").textContent && question.value === "" && $("historyView").hidden && $("task").hidden) {
    panel.hidden = true;
    resize();
  }
}

function renderStatus(next: PillStatus): void {
  status = next;
  dot.className = `dot ${next.online ? (next.ai ? "online" : "noai") : "offline"}`;
  dot.title = next.text;
  dot.setAttribute("aria-label", next.text);
  if (state === "idle" || state === "offline") setState(next.online ? "idle" : "offline");
}

function renderTasks(tasks: TaskSummary[]): void {
  const task = tasks.find((task) => !["completed", "failed", "cancelled"].includes(task.state));
  const box = $("task");
  if (!task) {
    box.hidden = true;
    delete box.dataset.id;
    hidePanelIfEmpty();
    return;
  }
  box.hidden = false;
  box.dataset.id = task.id;
  $("taskText").textContent = task.waiting ? fmt("taskWaiting") : fmt("taskRunning", { step: task.step ?? task.state });
  $("cancelTask").textContent = fmt("cancelTask");
  panel.hidden = false;
  if (state === "idle" && face) face.setState("working");
  resize();
}

async function renderHistory(): Promise<void> {
  const view = $("historyView");
  view.hidden = false;
  panel.hidden = false;
  const list = $("messages");
  list.replaceChildren();
  const [history, conversations] = await Promise.all([ezo.recentHistory(), ezo.conversations()]);
  const select = $<HTMLSelectElement>("conversations");
  const fresh = document.createElement("option");
  fresh.value = "";
  fresh.textContent = fmt("newConversation");
  select.replaceChildren(
    fresh,
    ...(conversations.conversations ?? []).map((c) => {
      const option = document.createElement("option");
      option.value = c.id;
      option.textContent = c.title || "…";
      return option;
    }),
  );
  select.value = history.conversationId ?? "";
  if (!history.ok) {
    const item = document.createElement("li");
    item.className = "muted";
    item.textContent = history.message ?? fmt("historyUnavailable");
    list.append(item);
  } else if ((history.messages ?? []).length === 0) {
    const item = document.createElement("li");
    item.className = "muted";
    item.textContent = fmt("noHistory");
    list.append(item);
  } else {
    for (const message of history.messages ?? []) {
      const item = document.createElement("li");
      item.className = message.role === "user" ? "me" : "ezo";
      item.textContent = message.content;
      list.append(item);
    }
  }
  resize();
  list.scrollTop = list.scrollHeight;
}

async function startListening(): Promise<void> {
  stopSpeaking();
  if (!media.microphone) {
    setState("error", fmt("micOff"));
    showPanel("", fmt("micOff"));
    return;
  }
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
  } catch {
    setState("error", fmt("micDenied"));
    showPanel("", fmt("micDeniedDetail"));
    return;
  }
  chunks = [];
  cancelled = false;
  const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus") ? "audio/webm;codecs=opus" : "audio/webm";
  recorder = new MediaRecorder(stream, { mimeType });
  recorder.ondataavailable = (event) => event.data.size && chunks.push(event.data);
  recorder.onstop = () => void finishRecording(mimeType);
  recorder.start();
  followLevel(stream);
  setState("listening");
  renderMedia();
  recordingTimer = window.setTimeout(() => stopListening(), MAX_RECORDING_MS);
}

function stopListening(cancel = false): void {
  cancelled = cancel;
  window.clearTimeout(recordingTimer);
  followLevel(null);
  if (recorder && recorder.state !== "inactive") recorder.stop();
  stream?.getTracks().forEach((track) => track.stop()); // the OS mic indicator turns off here
  stream = null;
  renderMedia();
}

async function finishRecording(mimeType: string): Promise<void> {
  recorder = null;
  if (cancelled || chunks.length === 0) {
    setState("idle");
    return;
  }
  const audio = await new Blob(chunks, { type: mimeType }).arrayBuffer();
  chunks = [];
  const turn = ++turnId;
  setState("recognizing");
  handle(await ezo.sendAudio(audio, mimeType), turn);
}

function handle(response: TurnResponse, turn: number): void {
  if (turn !== turnId || response.cancelled) return; // the owner pressed stop meanwhile
  if (response.error) {
    setState("error", response.error.slice(0, 60));
    showPanel(response.transcript ?? "", response.error);
    return;
  }
  showPanel(response.transcript ?? "", [response.reply, response.notice].filter(Boolean).join("\n\n"));
  if (response.audio && response.audio.data.byteLength > 0) {
    const url = URL.createObjectURL(new Blob([response.audio.data.slice()], { type: response.audio.mimeType }));
    const current = new Audio(url);
    current.volume = voiceVolume;
    player = current;
    current.onplaying = () => followLevel(current);
    current.onended = () => {
      URL.revokeObjectURL(url);
      followLevel(null);
      if (player === current) setState(response.acted ? "success" : "idle");
    };
    setState("speaking");
    void player.play().catch(() => setState("error", fmt("readAloudFailed")));
  } else {
    setState(response.acted ? "success" : "idle", response.acted ? fmt("acted") : undefined);
  }
}

function stopSpeaking(): void {
  followLevel(null);
  if (player) {
    player.pause();
    player = null;
  }
}

/** Stops whatever is happening: recording, the request on the server, or the voice. */
function stopEverything(detail?: string): void {
  if (state === "listening") stopListening(true);
  if (BUSY.has(state)) {
    turnId += 1;
    ezo.cancelTurn();
  }
  stopSpeaking();
  setState("idle", detail);
}

function toggle(): void {
  if (state === "listening") stopListening();
  else if (state === "speaking") stopEverything();
  else if (!BUSY.has(state)) void startListening();
}

$("orb").addEventListener("click", toggle);
$("expand").addEventListener("click", () => ezo.setExpanded(!expanded));
$("cameraToggle").addEventListener("click", () => (vision.camera !== "off" ? stopCamera() : void startCamera()));
$("clapToggle").addEventListener("click", () => void toggleClap());
$("stageFace").addEventListener("pointermove", (event) => {
  const rect = (event.currentTarget as HTMLElement).getBoundingClientRect();
  const gaze = { yaw: ((event.clientX - rect.left) / rect.width) * 2 - 1, pitch: 1 - ((event.clientY - rect.top) / rect.height) * 2 };
  if (adapter) adapter.pointerGaze(gaze, "pointer");
  else face?.setGaze(gaze);
});
$("stageFace").addEventListener("pointerleave", () => (adapter ? adapter.pointerGaze(null) : face?.setGaze(null)));
stopButton.addEventListener("click", () => stopEverything(fmt("stopped")));
$("gear").addEventListener("click", () => ezo.openSettings());
$("keyboard").addEventListener("click", () => {
  panel.hidden = false;
  ezo.setFocusable(true);
  resize();
  question.focus();
});
$("history").addEventListener("click", () => {
  if (!$("historyView").hidden) {
    $("historyView").hidden = true;
    hidePanelIfEmpty();
    resize();
    return;
  }
  ezo.setFocusable(true);
  void renderHistory();
});
$<HTMLSelectElement>("conversations").addEventListener("change", async (event) => {
  const id = (event.target as HTMLSelectElement).value || null;
  await ezo.switchConversation(id);
  void renderHistory();
});
$("newConversation").addEventListener("click", async () => {
  await ezo.switchConversation(null);
  void renderHistory();
});
$("cancelTask").addEventListener("click", async () => {
  const id = $("task").dataset.id;
  if (id) await ezo.cancelTask(id);
});
question.addEventListener("blur", () => {
  ezo.setFocusable(false);
  hidePanelIfEmpty();
});
$("ask").addEventListener("submit", async (event) => {
  event.preventDefault();
  const text = question.value.trim();
  if (!text || BUSY.has(state)) return;
  question.value = "";
  ezo.setFocusable(false); // give focus back to the app you were using (for dictation)
  const turn = ++turnId;
  setState("thinking");
  handle(await ezo.sendText(text), turn);
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    stopEverything();
    panel.hidden = true;
    $("historyView").hidden = true;
    ezo.setFocusable(false);
    resize();
  }
});

function applyInit(init: PillInit): void {
  t = init.strings;
  shortcut = init.shortcut;
  document.documentElement.lang = init.language;
  media = init.media ?? media;
  lowPower = init.lowPower ?? false;
  voiceVolume = typeof init.voiceVolume === "number" ? Math.min(1, Math.max(0, init.voiceVolume)) : 1;
  if (player) player.volume = voiceVolume;
  face?.setLowPower(lowPower);
  clapSettings = init.clap ?? clapSettings;
  if (!media.camera) stopCamera();
  if (!clapSettings.listening || !media.microphone) perception?.stopClap();
  if (!media.microphone && state === "listening") stopListening(true);
  $("expand").setAttribute("aria-label", expanded ? fmt("collapse") : fmt("expand"));
  $("expand").title = expanded ? fmt("collapse") : fmt("expand");
  renderCamera();
  $("orb").setAttribute("aria-label", fmt("talk"));
  $("orb").title = `${fmt("talk")} (${shortcut})`;
  $("keyboard").setAttribute("aria-label", fmt("type"));
  $("keyboard").title = fmt("type");
  $("history").setAttribute("aria-label", fmt("history"));
  $("history").title = fmt("history");
  stopButton.setAttribute("aria-label", fmt("stop"));
  stopButton.title = fmt("stop");
  $("gear").setAttribute("aria-label", fmt("settings"));
  $("gear").title = `${fmt("settings")} · ${fmt("showHideHint")}`;
  question.placeholder = fmt("typePlaceholder");
  $("conversations").setAttribute("aria-label", fmt("history"));
  $("newConversation").textContent = fmt("newConversation");
  renderStatus(init.status);
  setState(state);
}

ezo.onToggle(toggle);
ezo.onNotice((text) => showPanel("", String(text)));
ezo.onError((text) => {
  setState("error", String(text).slice(0, 60));
  showPanel("", String(text));
});
ezo.onStage((stage) => {
  // Stages describe the turn in flight; one that arrives after the turn ended or was
  // stopped must not wake the pill up again.
  const inFlight = state === "listening" || state === "recognizing" || state === "thinking" || state === "working";
  if (inFlight && (stage === "recognizing" || stage === "thinking" || stage === "working")) setState(stage);
});
ezo.onStatus((next) => renderStatus(next as PillStatus));
ezo.onTasks((tasks) => renderTasks(tasks as TaskSummary[]));
ezo.onInit((init) => applyInit(init as PillInit));
// Hidden (Ctrl+Alt+H, tray, quitting): release the microphone and the camera, stop drawing.
ezo.onVisibility?.((next) => {
  visible = next !== false;
  if (!visible) {
    if (state === "listening") stopListening(true);
    stopSpeaking();
    reaction.stop();
  }
  perception?.setVisible(visible); // hidden: camera and clap microphone off, nothing restarts by itself
  face?.setActive(visible);
  renderCamera();
});
ezo.onExpanded?.((next) => setExpanded(next === true));
mountFace();
void loadVisionAssets(VISION_BASE).then((result) => {
  readiness = result;
  if (expanded) mountPerception();
  renderCamera();
  reportDiagnostics();
});
void ezo.init().then((init) => {
  applyInit(init);
  void ezo.tasks().then(renderTasks);
});
