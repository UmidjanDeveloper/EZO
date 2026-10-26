// The floating pill: idle → listening → recognizing → thinking/working → speaking, always
// with a visible state and a real stop. Audio is recorded only while the red listening
// state is shown. Every word comes from the main process in the owner's language.
import { createLevelMeter, EzoAvatar, type AvatarState, type LevelMeter } from "@ezo/avatar";

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
  refreshStatus(): Promise<PillStatus>;
  recentHistory(): Promise<History>;
  conversations(): Promise<{ ok: boolean; conversations?: { id: string; title: string }[]; message?: string }>;
  switchConversation(id: string | null): Promise<string | null>;
  tasks(): Promise<TaskSummary[]>;
  cancelTask(id: string): Promise<{ ok: boolean }>;
  onToggle(callback: () => void): void;
  onNotice(callback: (text: unknown) => void): void;
  onError(callback: (text: unknown) => void): void;
  onStage(callback: (stage: unknown) => void): void;
  onStatus(callback: (status: unknown) => void): void;
  onTasks(callback: (tasks: unknown) => void): void;
  onInit(callback: (init: unknown) => void): void;
}

const ezo = (window as unknown as { ezo: EzoBridge }).ezo;
type State = AvatarState;

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
const pill = $("pill");
const label = $("label");
const hint = $("hint");
const panel = $("panel");
const dot = $("dot");
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

// EZO's humanoid face follows the microphone while listening and its own voice while speaking.
const face: EzoAvatar | null = EzoAvatar.supported()
  ? new EzoAvatar($<HTMLCanvasElement>("face"), { framing: "head", quality: "low", terrain: false, describe: (s) => t[s] ?? s })
  : null;
if (face) document.body.classList.add("has-face");
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
  requestAnimationFrame(() => ezo.setHeight(panel.hidden ? 72 : document.body.scrollHeight + 4));
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
  recordingTimer = window.setTimeout(() => stopListening(), MAX_RECORDING_MS);
}

function stopListening(cancel = false): void {
  cancelled = cancel;
  window.clearTimeout(recordingTimer);
  followLevel(null);
  if (recorder && recorder.state !== "inactive") recorder.stop();
  stream?.getTracks().forEach((track) => track.stop()); // the OS mic indicator turns off here
  stream = null;
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
void ezo.init().then((init) => {
  applyInit(init);
  void ezo.tasks().then(renderTasks);
});
