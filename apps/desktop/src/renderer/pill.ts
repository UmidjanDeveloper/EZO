// The floating pill: idle → listening → thinking → speaking, always with a visible state
// and a stop button. Audio is recorded only while the red listening state is shown.

interface TurnResponse {
  transcript?: string;
  reply?: string;
  acted?: boolean;
  audio?: { mimeType: string; data: Uint8Array };
  error?: string;
  notice?: string;
}

interface EzoBridge {
  sendAudio(audio: ArrayBuffer, mimeType: string): Promise<TurnResponse>;
  sendText(text: string): Promise<TurnResponse>;
  openSettings(): void;
  setFocusable(focusable: boolean): void;
  setHeight(height: number): void;
  onToggle(callback: () => void): void;
  onNotice(callback: (text: string) => void): void;
}

const ezo = (window as unknown as { ezo: EzoBridge }).ezo;
type State = "idle" | "listening" | "thinking" | "speaking" | "error";

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
const pill = $("pill");
const label = $("label");
const hint = $("hint");
const panel = $("panel");
const stopButton = $<HTMLButtonElement>("stop");
const question = $<HTMLInputElement>("question");

const MAX_RECORDING_MS = 30_000;
let state: State = "idle";
let recorder: MediaRecorder | null = null;
let stream: MediaStream | null = null;
let chunks: Blob[] = [];
let cancelled = false;
let player: HTMLAudioElement | null = null;
let recordingTimer: number | undefined;

const LABELS: Record<State, [string, string]> = {
  idle: ["EZO", "Ctrl+Alt+Space — gapiring"],
  listening: ["Tinglayapman…", "Tugatish uchun yana bosing"],
  thinking: ["O‘ylayapman…", "EZO serveriga so‘rov yuborildi"],
  speaking: ["Gapiryapman…", "To‘xtatish uchun ■"],
  error: ["Xatolik", "Batafsil pastda"],
};

function setState(next: State, detail?: string): void {
  state = next;
  pill.className = `pill ${next}`;
  const [title, sub] = LABELS[next];
  label.textContent = title;
  hint.textContent = detail ?? sub;
  stopButton.hidden = next === "idle" || next === "error";
}

function showPanel(transcript: string, reply: string): void {
  panel.hidden = false;
  $("transcript").textContent = transcript ? `Siz: ${transcript}` : "";
  $("reply").textContent = reply;
  requestAnimationFrame(() => ezo.setHeight(document.body.scrollHeight + 4));
}

function hidePanelIfEmpty(): void {
  if (!$("reply").textContent && question.value === "") {
    panel.hidden = true;
    ezo.setHeight(72);
  }
}

async function startListening(): Promise<void> {
  stopSpeaking();
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
  } catch {
    setState("error", "Mikrofonga ruxsat berilmadi");
    showPanel("", "Mikrofonga kirish rad etildi yoki mikrofon topilmadi. Windows sozlamalari → Maxfiylik → Mikrofon.");
    return;
  }
  chunks = [];
  cancelled = false;
  const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus") ? "audio/webm;codecs=opus" : "audio/webm";
  recorder = new MediaRecorder(stream, { mimeType });
  recorder.ondataavailable = (event) => event.data.size && chunks.push(event.data);
  recorder.onstop = () => void finishRecording(mimeType);
  recorder.start();
  setState("listening");
  recordingTimer = window.setTimeout(() => stopListening(), MAX_RECORDING_MS);
}

function stopListening(cancel = false): void {
  cancelled = cancel;
  window.clearTimeout(recordingTimer);
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
  setState("thinking");
  handle(await ezo.sendAudio(audio, mimeType));
}

function handle(response: TurnResponse): void {
  if (response.error) {
    setState("error", response.error.slice(0, 60));
    showPanel(response.transcript ?? "", response.error);
    return;
  }
  showPanel(response.transcript ?? "", [response.reply, response.notice].filter(Boolean).join("\n\n"));
  if (response.audio && response.audio.data.byteLength > 0) {
    const url = URL.createObjectURL(new Blob([response.audio.data.slice()], { type: response.audio.mimeType }));
    player = new Audio(url);
    player.onended = () => {
      URL.revokeObjectURL(url);
      setState("idle");
    };
    setState("speaking");
    void player.play().catch(() => setState("idle"));
  } else {
    setState("idle", response.acted ? "Bajarildi" : undefined);
  }
}

function stopSpeaking(): void {
  if (player) {
    player.pause();
    player = null;
  }
}

function toggle(): void {
  if (state === "listening") stopListening();
  else if (state === "speaking") {
    stopSpeaking();
    setState("idle");
  } else if (state !== "thinking") void startListening();
}

$("orb").addEventListener("click", toggle);
stopButton.addEventListener("click", () => {
  if (state === "listening") stopListening(true);
  stopSpeaking();
  setState("idle", "To‘xtatildi");
});
$("gear").addEventListener("click", () => ezo.openSettings());
$("keyboard").addEventListener("click", () => {
  panel.hidden = false;
  ezo.setFocusable(true);
  ezo.setHeight(document.body.scrollHeight + 4);
  question.focus();
});
question.addEventListener("blur", () => {
  ezo.setFocusable(false);
  hidePanelIfEmpty();
});
$("ask").addEventListener("submit", async (event) => {
  event.preventDefault();
  const text = question.value.trim();
  if (!text || state === "thinking") return;
  question.value = "";
  ezo.setFocusable(false); // give focus back to the app you were using (for dictation)
  setState("thinking");
  handle(await ezo.sendText(text));
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    stopListening(true);
    stopSpeaking();
    panel.hidden = true;
    ezo.setFocusable(false);
    ezo.setHeight(72);
    setState("idle");
  }
});
ezo.onToggle(toggle);
ezo.onNotice((text) => setState("error", text));
setState("idle");
