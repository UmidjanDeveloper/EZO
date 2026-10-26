import "./styles.css";
import { Camera, CameraResultType, CameraSource } from "@capacitor/camera";
import { LocalNotifications } from "@capacitor/local-notifications";
import { FilePicker } from "@capawesome/capacitor-file-picker";
import { createLevelMeter, createVoiceFrame, EzoAvatar, type AvatarState, type LevelMeter, type VoiceFrame } from "@ezo/avatar";
import { ApiError, createApi, type Api, type IeltsAdvance, type JarvisTask, type Lang, type Message, type ServerStatus } from "./api";
import { base64Bytes, documentPrompt, isStudentDocument, jobMessage, MAX_STUDENT_BYTES } from "./documents";
import { Recorder } from "./recorder";
import { openOrShare } from "./share";
import { loadPrefs, normalizeApiUrl, readToken, savePrefs, writeToken, type Prefs } from "./store";
import { format, strings, UI_LANGUAGES, type Strings } from "./strings";

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
let prefs: Prefs = loadPrefs();
let t: Strings = strings(prefs.language);
let api: Api | null = null;
let turn: AbortController | null = null;
const recorder = new Recorder();
let player: HTMLAudioElement | null = null;
let server: ServerStatus = { online: false, ai: false, voice: false, providers: [] };

function errorText(error: unknown): string {
  return error instanceof ApiError ? error.message : format(t.api.error, { message: (error as Error).message ?? String(error) });
}

function setStatus(text: string, kind: "info" | "busy" | "error" = "info"): void {
  const status = $("status");
  status.textContent = text;
  status.className = `status ${kind}`;
}

/** A client for one user action; a later action, or closing the stage, aborts the earlier one. */
function client(): Api | null {
  if (!api) return null;
  turn?.abort();
  turn = new AbortController();
  return createApi(prefs.apiUrl, currentToken, fetch.bind(globalThis), { lang: prefs.language, signal: turn.signal });
}
let currentToken: string | null = null;

async function connect(): Promise<boolean> {
  if (!prefs.apiUrl) return false;
  currentToken = await readToken();
  api = createApi(prefs.apiUrl, currentToken, fetch.bind(globalThis), { lang: prefs.language });
  return true;
}

// ---------- words ----------
function applyStrings(): void {
  t = strings(prefs.language);
  document.documentElement.lang = prefs.language;
  for (const node of document.querySelectorAll<HTMLElement>("[data-i18n]")) {
    const [section, key] = node.dataset.i18n!.split(".") as [keyof Strings, string];
    node.textContent = (t[section] as unknown as Record<string, string>)[key] ?? node.dataset.i18n!;
  }
  $("conversation").setAttribute("aria-label", t.chat.conversation);
  $("refresh").setAttribute("aria-label", t.chat.refresh);
  $("document").setAttribute("aria-label", t.chat.document);
  $("camera").setAttribute("aria-label", t.chat.camera);
  $("send").setAttribute("aria-label", t.chat.send);
  $("mic").setAttribute("aria-label", t.chat.speak);
  $<HTMLInputElement>("input").placeholder = t.chat.placeholder;
  $<HTMLInputElement>("taskText").placeholder = t.tasks.placeholder;
  $<HTMLTextAreaElement>("ieltsAnswer").placeholder = t.ielts.answerPlaceholder;
  $("ieltsMic").textContent = `🎤 ${t.ielts.speakAnswer}`;
  $<HTMLInputElement>("projectName").placeholder = t.more.newProject;
  $<HTMLInputElement>("memoryInput").placeholder = t.more.memoryPlaceholder;
  $<HTMLInputElement>("reminderText").placeholder = t.more.reminderPlaceholder;
  $<HTMLInputElement>("token").placeholder = t.more.tokenPlaceholder;
  $("voiceStage").setAttribute("aria-label", t.voice.title);
  $("stageClose").setAttribute("aria-label", t.voice.close);
  document.querySelector(".langs")!.setAttribute("aria-label", t.voice.language);
  const auto = document.querySelector<HTMLButtonElement>('.langs button[data-lang="auto"]')!;
  auto.textContent = t.voice.auto;
  auto.title = t.voice.autoHint;
  for (const select of [$<HTMLSelectElement>("language"), $<HTMLSelectElement>("welcomeLanguage")]) {
    select.replaceChildren(
      ...UI_LANGUAGES.map((l) => {
        const option = document.createElement("option");
        option.value = l.code;
        option.textContent = l.label;
        option.selected = l.code === prefs.language;
        return option;
      }),
    );
  }
  renderStatusDot();
}

function setLanguage(language: Lang): void {
  prefs = { ...prefs, language };
  savePrefs(prefs);
  if (api) api = createApi(prefs.apiUrl, currentToken, fetch.bind(globalThis), { lang: language });
  applyStrings();
}

// ---------- server status ----------
function renderStatusDot(): void {
  const dot = $("dot");
  dot.className = `dot ${server.online ? (server.ai ? "online" : "noai") : "offline"}`;
  const text = server.online ? (server.ai ? t.status.online : t.status.noAi) : t.status.offline;
  dot.title = text;
  dot.setAttribute("aria-label", text);
  $("offlineBanner").hidden = server.online || !prefs.apiUrl;
}

async function refreshStatus(): Promise<void> {
  if (!api) return;
  try {
    server = await api.status();
  } catch (error) {
    // A reachable server that refuses the token still counts as reachable.
    const reachable = error instanceof ApiError && error.status > 0;
    server = { online: reachable, ai: false, voice: false, providers: [] };
  }
  renderStatusDot();
}

// ---------- tabs ----------
function showTab(name: string): void {
  for (const tab of document.querySelectorAll<HTMLElement>("[data-tab]")) tab.hidden = tab.dataset.tab !== name;
  for (const button of document.querySelectorAll<HTMLButtonElement>("nav button")) button.classList.toggle("active", button.dataset.go === name);
  document.querySelector("nav")!.hidden = name === "welcome";
  if (name === "chat") void refreshConversations();
  if (name === "tasks") void loadTasks();
  if (name === "learn") void loadIelts();
  if (name === "files") void loadFiles();
  if (name === "more") {
    void loadProjects();
    void loadMemories();
  }
}

// ---------- chat ----------
function renderMessages(messages: Pick<Message, "role" | "content">[]): void {
  const list = $("messages");
  list.replaceChildren(
    ...messages.map((m) => {
      const bubble = document.createElement("div");
      bubble.className = `bubble ${m.role}`;
      bubble.textContent = m.content;
      return bubble;
    }),
  );
  list.scrollTop = list.scrollHeight;
}

function appendMessage(role: "user" | "assistant", content: string): HTMLDivElement {
  const bubble = document.createElement("div");
  bubble.className = `bubble ${role}`;
  bubble.textContent = content;
  $("messages").append(bubble);
  $("messages").scrollTop = $("messages").scrollHeight;
  return bubble;
}

async function refreshConversations(): Promise<void> {
  if (!api) return;
  try {
    const conversations = await api.conversations();
    const select = $<HTMLSelectElement>("conversation");
    const fresh = document.createElement("option");
    fresh.value = "";
    fresh.textContent = t.chat.newConversation;
    select.replaceChildren(
      fresh,
      ...conversations.map((c) => {
        const option = document.createElement("option");
        option.value = c.id;
        option.textContent = c.title || t.chat.untitled;
        return option;
      }),
    );
    select.value = prefs.conversationId ?? "";
    if (prefs.conversationId) renderMessages(await api.messages(prefs.conversationId));
    else renderMessages([]);
    setStatus(t.status.connected);
    void refreshStatus();
  } catch (error) {
    setStatus(errorText(error), "error");
    void refreshStatus();
  }
}

async function ask(text: string, channel: "text" | "voice", heard: Lang | null = null): Promise<{ content: string; language: Lang | null } | null> {
  const run = client();
  if (!run) {
    setStatus(t.status.connectFirst, "error");
    return null;
  }
  const mine = appendMessage("user", text);
  setStatus(t.status.thinking, "busy");
  try {
    const { conversationId, reply, language } = await run.chat(text, prefs.conversationId, prefs.projectId, channel, heard);
    if (prefs.conversationId !== conversationId) {
      prefs = { ...prefs, conversationId };
      savePrefs(prefs);
    }
    appendMessage("assistant", reply.content);
    setStatus(t.status.ready);
    return { content: reply.content, language: language ?? heard };
  } catch (error) {
    if (error instanceof ApiError && error.code === "cancelled") {
      mine.remove();
      return null;
    }
    // The message stays visible with a retry; nothing pretends it was sent.
    mine.classList.add("failed");
    const retry = document.createElement("button");
    retry.type = "button";
    retry.className = "retry";
    retry.textContent = `${t.chat.sendFailed} ${t.status.retry}`;
    retry.addEventListener("click", () => {
      mine.remove();
      void ask(text, channel, heard);
    });
    mine.append(retry);
    setStatus(errorText(error), "error");
    void refreshStatus();
    return null;
  }
}

// --- voice stage: EZO's humanoid, full screen ------------------------------------------------

let avatar: EzoAvatar | null = null;
let frame: VoiceFrame | null = null;
let meter: LevelMeter | null = null;
let meterFrame = 0;
let voiceBusy = false;

function stageState(state: AvatarState, status: string): void {
  avatar?.setState(state);
  $("stageStatus").textContent = status;
  $("stageMic").textContent = state === "listening" ? "■" : "🎤";
  $("stageMic").setAttribute("aria-label", state === "listening" ? t.voice.stop : t.voice.start);
}

function followLevel(source: MediaStream | HTMLMediaElement | null): void {
  cancelAnimationFrame(meterFrame);
  meter?.close();
  meter = source ? createLevelMeter(source) : null;
  const tick = () => {
    if (!meter) return;
    avatar?.setLevel(meter.read());
    meterFrame = requestAnimationFrame(tick);
  };
  if (meter) meterFrame = requestAnimationFrame(tick);
}

function renderLanguage(): void {
  for (const button of document.querySelectorAll<HTMLButtonElement>(".langs button")) {
    button.setAttribute("aria-pressed", String(button.dataset.lang === prefs.voiceLanguage));
  }
}

function openStage(): void {
  $("voiceStage").hidden = false;
  if (!avatar) {
    avatar = new EzoAvatar($<HTMLCanvasElement>("avatar"), { framing: "bust", describe: (s) => t.voice.words[s] });
    frame = createVoiceFrame($("avatarBox"), { words: t.voice.words });
    frame.follow(avatar);
  }
  renderLanguage();
  if (!server.online) stageState("offline", t.voice.offline);
  else stageState("idle", t.voice.tapToTalk);
}

function closeStage(): void {
  if (recorder.active) void recorder.stop();
  turn?.abort(); // an in-flight transcription, answer or voice stops with the stage
  player?.pause();
  followLevel(null);
  frame?.destroy();
  frame = null;
  avatar?.destroy(); // frees the GPU while the stage is closed
  avatar = null;
  voiceBusy = false;
  $("voiceStage").hidden = true;
}

/** Plays EZO's reply in the reply's language; resolves when it has finished. */
async function speak(run: Api, text: string, language: Lang | null): Promise<void> {
  if (!prefs.speakReplies) return;
  try {
    const audio = await run.speak(text, language);
    player?.pause();
    const current = new Audio(URL.createObjectURL(audio));
    player = current;
    await new Promise<void>((resolve) => {
      current.onplaying = () => followLevel(current);
      current.onended = current.onpause = current.onerror = () => resolve();
      current.play().catch(() => resolve());
    });
  } catch (error) {
    if (error instanceof ApiError && error.code === "cancelled") return;
    setStatus(format(t.voice.textOnly, { error: errorText(error) }), "error");
  } finally {
    followLevel(null);
  }
}

async function startListening(): Promise<void> {
  player?.pause();
  turn?.abort();
  try {
    await recorder.start();
  } catch (error) {
    const denied = error instanceof DOMException && (error.name === "NotAllowedError" || error.name === "SecurityError");
    stageState("error", denied ? t.voice.micDenied : t.voice.micMissing);
    return;
  }
  followLevel(recorder.liveStream);
  $("stageHeard").textContent = "";
  stageState("listening", t.voice.listening);
}

async function finishListening(): Promise<void> {
  if (voiceBusy) return;
  voiceBusy = true;
  followLevel(null);
  const run = client();
  try {
    const audio = await recorder.stop();
    if (!run) return stageState("error", t.status.connectFirst);
    if (!audio) return stageState("idle", t.voice.nothingRecorded);
    stageState("recognizing", t.voice.recognizing);
    const fixed = prefs.voiceLanguage === "auto" ? null : prefs.voiceLanguage;
    const { text, language } = await run.transcribe(audio, fixed);
    if (!text) return stageState("idle", t.voice.nothingHeard);
    $("stageHeard").textContent = text;
    stageState("thinking", t.voice.thinking);
    const reply = await ask(text, "voice", language);
    if (!reply) return stageState($("status").className.includes("error") ? "error" : "idle", $("status").textContent ?? "");
    $("stageReply").textContent = reply.content;
    stageState("speaking", t.voice.speaking);
    await speak(run, reply.content, reply.language);
    if (!$("voiceStage").hidden && !recorder.active) stageState("idle", t.voice.again);
  } catch (error) {
    if (error instanceof ApiError && error.code === "cancelled") return;
    stageState("error", errorText(error));
  } finally {
    voiceBusy = false;
  }
}

async function toggleStageMic(): Promise<void> {
  if (recorder.active) return finishListening();
  // Pressing while EZO speaks, thinks or recognises interrupts it and listens again.
  if (voiceBusy) {
    turn?.abort();
    player?.pause();
    voiceBusy = false;
  }
  await startListening();
}

// ---------- photo and documents ----------
async function explainPhoto(): Promise<void> {
  const run = client();
  if (!run) return;
  try {
    const photo = await Camera.getPhoto({
      source: CameraSource.Prompt,
      resultType: CameraResultType.Base64,
      quality: 70,
      width: 1600,
      correctOrientation: true,
      promptLabelHeader: t.photo.header,
      promptLabelPhoto: t.photo.gallery,
      promptLabelPicture: t.photo.take,
    });
    if (!photo.base64String) return;
    const bytes = Uint8Array.from(atob(photo.base64String), (c) => c.charCodeAt(0));
    const mime = photo.format === "png" ? "image/png" : "image/jpeg";
    const question = $<HTMLInputElement>("input").value.trim() || t.photo.question;
    $<HTMLInputElement>("input").value = "";
    appendMessage("user", `📷 ${question}`);
    setStatus(t.photo.analyzing, "busy");
    const answer = await run.describeImage(new Blob([bytes], { type: mime }), question, prefs.language);
    appendMessage("assistant", answer);
    setStatus(t.photo.done);
    await speak(run, answer, prefs.language);
  } catch (error) {
    if ((error as Error).message?.toLowerCase().includes("cancel")) return;
    setStatus(errorText(error), "error");
  }
}

async function summarizeDocument(): Promise<void> {
  try {
    const picked = await FilePicker.pickFiles({ limit: 1, readData: true });
    const file = picked.files[0];
    if (!file) return;
    if (isStudentDocument(file.name)) return await readWithStudent(file.name, file.data);
    const result = documentPrompt(file.name, file.data);
    if (!result.ok) return setStatus(result.reason, "error");
    if (result.truncated) setStatus(t.docs.truncated, "info");
    await ask(result.prompt, "text");
  } catch (error) {
    if ((error as Error).message?.toLowerCase().includes("cancel")) return;
    setStatus(errorText(error), "error");
  }
}

/** PDF/DOCX/EPUB/scans: upload to EZO Student, follow the real job, then a cited summary. */
async function readWithStudent(name: string, base64: string | undefined): Promise<void> {
  const run = client();
  if (!run) return setStatus(t.status.connectFirst, "error");
  if (!base64) return setStatus(t.docs.unreadable, "error");
  const bytes = base64Bytes(base64);
  if (bytes.length > MAX_STUDENT_BYTES) return setStatus(t.docs.tooLarge, "error");
  let job = await run.uploadStudent(name, bytes);
  const started = Date.now();
  appendMessage("user", `📄 ${name}`);
  while (job.state === "queued" || job.state === "running") {
    const waited = Math.round((Date.now() - started) / 1000);
    setStatus(jobMessage(job.state, waited, null, t.docs), "info");
    if (waited >= 90) return; // honest: the worker may not be running; the job stays queued
    await new Promise((resolve) => setTimeout(resolve, 3000));
    job = await run.studentJob(job.id);
  }
  setStatus(jobMessage(job.state, 0, job.error_message, t.docs), job.state === "completed" ? "info" : "error");
  if (job.state !== "completed") return;
  const summary = await run.studentSummary(job.document_id, prefs.language);
  appendMessage("assistant", summary.text + (summary.citations ? `\n\n${format(t.docs.citations, { n: summary.citations })}` : ""));
  setStatus("");
  await speak(run, summary.text, prefs.language);
}

// ---------- JARVIS tasks ----------
const STEP_ICON: Record<string, string> = { "files.latest_documents": "📂", "document.extract": "📄", "compute.percentages": "％", "document.convert_pdf": "🧾", "document.report_pdf": "📑", "telegram.send": "✈" };

function stateWord(state: string): string {
  return (t.tasks.state as Record<string, string>)[state] ?? state;
}

function renderTasks(tasks: JarvisTask[]): void {
  const list = $("taskList");
  if (tasks.length === 0) {
    const item = document.createElement("li");
    item.className = "muted";
    item.textContent = t.tasks.none;
    list.replaceChildren(item);
    return;
  }
  list.replaceChildren(
    ...tasks.map((task) => {
      const item = document.createElement("li");
      const title = document.createElement("div");
      title.className = "title";
      title.textContent = task.request_text;
      const current = task.steps.find((s) => !["completed", "skipped", "cancelled"].includes(s.state));
      const state = document.createElement("div");
      state.className = `state ${current?.state === "awaiting_authorization" ? "waiting" : task.state}`;
      state.textContent = `${stateWord(task.state)}${current ? ` · ${STEP_ICON[current.action] ?? "•"} ${current.action}` : ""}`;
      item.append(title, state);
      if (task.report) {
        const report = document.createElement("p");
        report.className = "muted";
        report.textContent = `${t.tasks.report} ${task.report}`;
        item.append(report);
      }
      const row = document.createElement("div");
      row.className = "row";
      if (current?.state === "awaiting_authorization" && current.scope_sha256) {
        const what = document.createElement("p");
        what.className = "muted";
        const files = (current.output.documents ?? []).map((d) => d.filename).join(", ");
        what.textContent = format(t.tasks.approveWhat, { action: `${current.action}${current.output.recipient ? ` → ${current.output.recipient}` : ""}${files ? ` (${files})` : ""}` });
        item.append(what);
        for (const [label, approve] of [[t.tasks.approve, true], [t.tasks.deny, false]] as const) {
          const button = document.createElement("button");
          button.className = approve ? "small" : "ghost small";
          button.textContent = label;
          button.addEventListener("click", async () => {
            try {
              await api!.decideJarvisStep(task.id, current.id, current.scope_sha256!, approve);
              await loadTasks();
            } catch (error) {
              setStatus(errorText(error), "error");
            }
          });
          row.append(button);
        }
      }
      if (!["completed", "failed", "cancelled"].includes(task.state)) {
        const cancel = document.createElement("button");
        cancel.className = "ghost small";
        cancel.textContent = t.tasks.cancel;
        cancel.addEventListener("click", async () => {
          try {
            await api!.cancelJarvisTask(task.id);
            await loadTasks();
          } catch (error) {
            setStatus(errorText(error), "error");
          }
        });
        row.append(cancel);
      }
      if (row.children.length) item.append(row);
      return item;
    }),
  );
}

async function loadTasks(): Promise<void> {
  if (!api) return;
  try {
    const [tasks, capabilities] = await Promise.all([api.jarvisTasks(), api.jarvisCapabilities()]);
    renderTasks(tasks);
    const features = Object.entries(capabilities.device_features).map(([name, f]) => `${name}: ${f.available ? t.tasks.available : t.tasks.unavailable}`);
    $("taskCapabilities").textContent = `${t.tasks.capabilities}: ${features.join(" · ")}`;
    const windows = capabilities.device_features.windows_downloads;
    if (windows && !windows.available) $("taskCapabilities").textContent += `\n${t.tasks.noDevice}`;
  } catch (error) {
    setStatus(errorText(error), "error");
  }
}

async function createTask(): Promise<void> {
  const text = $<HTMLInputElement>("taskText").value.trim();
  if (!text || !api) return;
  try {
    await api.createJarvisTask(text, prefs.language);
    $<HTMLInputElement>("taskText").value = "";
    await loadTasks();
  } catch (error) {
    setStatus(errorText(error), "error");
  }
}

// ---------- IELTS speaking practice ----------
let ielts: { id: string; part: number } | null = null;
let ieltsSpeechStart = 0;
let ieltsSpeechSeconds: number | null = null;

async function loadIelts(): Promise<void> {
  if (!api) return;
  try {
    const [cards, history] = await Promise.all([api.cueCards(), api.ieltsHistory().catch(() => [])]);
    const select = $<HTMLSelectElement>("cueCard");
    const any = document.createElement("option");
    any.value = "";
    any.textContent = t.ielts.anyCard;
    select.replaceChildren(
      any,
      ...cards.map((card) => {
        const option = document.createElement("option");
        option.value = card.id;
        option.textContent = card.task;
        return option;
      }),
    );
    $("ieltsHistory").textContent = format(t.ielts.history, { n: history.length });
  } catch (error) {
    setStatus(errorText(error), "error");
  }
}

function showIeltsPrompt(part: number, prompt: string | null): void {
  $("ieltsPart").textContent = format(t.ielts.part, { part });
  $("ieltsPrompt").textContent = prompt ?? "";
}

async function beginIelts(): Promise<void> {
  if (!api) return;
  try {
    const session = await api.startIelts($<HTMLSelectElement>("cueCard").value || null);
    ielts = { id: session.id, part: session.ielts_part ?? 1 };
    $("ieltsStart").hidden = true;
    $("ieltsRun").hidden = false;
    $("ieltsMetrics").hidden = true;
    $("ieltsDone").hidden = true;
    $("ieltsNew").hidden = true;
    $("ieltsForm").hidden = false;
    $("ieltsHeard").textContent = "";
    $("ieltsStatus").textContent = server.voice ? "" : t.ielts.voiceNote;
    showIeltsPrompt(ielts.part, session.current_prompt);
  } catch (error) {
    setStatus(errorText(error), "error");
  }
}

function renderIeltsMetrics(result: IeltsAdvance): void {
  const box = $("ieltsMetrics");
  const m = result.metrics;
  if (!m) {
    box.hidden = true;
    return;
  }
  const notes = prefs.language === "en" ? m.observations_en : m.observations_uz;
  const notice = prefs.language === "en" ? m.heuristic_notice_en : m.heuristic_notice_uz;
  box.replaceChildren();
  const title = document.createElement("p");
  title.className = "title";
  title.textContent = t.ielts.metrics;
  const lines = [
    format(t.ielts.words, { words: m.words, unique: m.unique_words }),
    format(t.ielts.fillers, { fillers: m.fillers }),
    ...(m.repeated.length ? [format(t.ielts.repeated, { list: m.repeated.join(", ") })] : []),
    ...(ieltsSpeechSeconds !== null ? [format(t.ielts.speechSeconds, { seconds: ieltsSpeechSeconds.toFixed(1) })] : []),
    ...notes,
  ];
  box.append(title, ...lines.map((line) => Object.assign(document.createElement("p"), { textContent: line })));
  const small = document.createElement("p");
  small.className = "muted";
  small.textContent = notice;
  box.append(small);
  box.hidden = false;
}

async function submitIelts(): Promise<void> {
  const answer = $<HTMLTextAreaElement>("ieltsAnswer").value.trim();
  if (!answer || !ielts || !api) return;
  $("ieltsStatus").textContent = t.status.thinking;
  try {
    const result = await api.ieltsAdvance(ielts.id, answer, ieltsSpeechSeconds);
    $<HTMLTextAreaElement>("ieltsAnswer").value = "";
    $("ieltsHeard").textContent = "";
    ieltsSpeechSeconds = null;
    renderIeltsMetrics(result);
    $("ieltsStatus").textContent = "";
    if (result.finished) {
      const done = $("ieltsDone");
      done.replaceChildren(
        Object.assign(document.createElement("p"), { className: "title", textContent: t.ielts.finished }),
        Object.assign(document.createElement("p"), { textContent: `${t.ielts.feedback} ${result.feedback ?? result.explanation_uz ?? ""}` }),
        Object.assign(document.createElement("p"), { className: "muted", textContent: t.ielts.band }),
      );
      done.hidden = false;
      $("ieltsForm").hidden = true;
      $("ieltsNew").hidden = false;
      ielts = null;
      return;
    }
    ielts.part = result.part;
    // The session holds the next question for the learner; `instruction` is examiner-facing.
    const session = await api.ieltsSession(ielts.id).catch(() => null);
    showIeltsPrompt(session?.ielts_part ?? result.part, session?.current_prompt ?? result.instruction);
  } catch (error) {
    $("ieltsStatus").textContent = errorText(error);
  }
}

/** Speak an IELTS answer: the phone measures the speaking time; the server transcribes. */
async function ieltsMic(): Promise<void> {
  if (!api) return;
  const button = $("ieltsMic");
  if (recorder.active) {
    const seconds = (Date.now() - ieltsSpeechStart) / 1000;
    button.textContent = `🎤 ${t.ielts.speakAnswer}`;
    $("ieltsStatus").textContent = t.ielts.recognizing;
    try {
      const audio = await recorder.stop();
      if (!audio) return void ($("ieltsStatus").textContent = t.voice.nothingRecorded);
      const { text } = await api.transcribe(audio, "en");
      if (!text) return void ($("ieltsStatus").textContent = t.voice.nothingHeard);
      ieltsSpeechSeconds = Math.round(seconds * 10) / 10;
      $<HTMLTextAreaElement>("ieltsAnswer").value = text;
      $("ieltsHeard").textContent = format(t.ielts.heard, { text });
      $("ieltsStatus").textContent = format(t.ielts.speechSeconds, { seconds: ieltsSpeechSeconds.toFixed(1) });
    } catch (error) {
      $("ieltsStatus").textContent = errorText(error);
    }
    return;
  }
  try {
    await recorder.start();
    ieltsSpeechStart = Date.now();
    button.textContent = `■ ${t.voice.stop}`;
    $("ieltsStatus").textContent = t.ielts.listening;
  } catch (error) {
    const denied = error instanceof DOMException && error.name === "NotAllowedError";
    $("ieltsStatus").textContent = denied ? t.voice.micDenied : t.voice.micMissing;
  }
}

// ---------- generated files ----------
async function loadFiles(): Promise<void> {
  if (!api) return;
  try {
    const artifacts = (await api.artifacts()).filter((a) => a.current_version);
    const list = $("fileList");
    if (artifacts.length === 0) {
      list.replaceChildren(Object.assign(document.createElement("li"), { className: "muted", textContent: t.files.none }));
      return;
    }
    list.replaceChildren(
      ...artifacts.map((artifact) => {
        const item = document.createElement("li");
        const version = artifact.current_version!;
        item.append(
          Object.assign(document.createElement("div"), { className: "title", textContent: artifact.title }),
          Object.assign(document.createElement("div"), {
            className: "state",
            textContent: `${version.filename} · ${Math.max(1, Math.round(version.file_size / 1024))} KB · ${format(t.files.version, { n: version.version_number })}`,
          }),
        );
        const open = document.createElement("button");
        open.className = "small";
        open.textContent = t.files.open;
        open.addEventListener("click", async () => {
          open.disabled = true;
          setStatus(t.files.downloading, "busy");
          try {
            const { blob, filename } = await api!.downloadArtifact(artifact.id);
            await openOrShare(blob, filename || version.filename, artifact.title);
            setStatus(t.files.shared);
          } catch (error) {
            setStatus(format(t.files.failed, { error: errorText(error) }), "error");
          } finally {
            open.disabled = false;
          }
        });
        const row = document.createElement("div");
        row.className = "row";
        row.append(open);
        item.append(row);
        return item;
      }),
    );
  } catch (error) {
    setStatus(errorText(error), "error");
  }
}

// ---------- projects, memory, reminders ----------
async function loadProjects(): Promise<void> {
  if (!api) return;
  try {
    const projects = await api.projects();
    const list = $("projectList");
    const none = document.createElement("li");
    none.textContent = prefs.projectId ? t.more.noProject : t.more.noProjectActive;
    none.addEventListener("click", () => chooseProject(null));
    list.replaceChildren(
      none,
      ...projects.map((p) => {
        const item = document.createElement("li");
        item.textContent = `${p.id === prefs.projectId ? "✓ " : ""}${p.name}`;
        item.addEventListener("click", () => chooseProject(p.id));
        return item;
      }),
    );
  } catch (error) {
    setStatus(errorText(error), "error");
  }
}

function chooseProject(id: string | null): void {
  prefs = { ...prefs, projectId: id, conversationId: null };
  savePrefs(prefs);
  setStatus(id ? t.more.projectChosen : t.more.projectCleared);
  void loadProjects();
}

async function loadMemories(): Promise<void> {
  if (!api) return;
  try {
    const memories = await api.memories();
    $("memoryList").replaceChildren(
      ...memories.map((m) => {
        const item = document.createElement("li");
        item.textContent = m.content;
        const remove = document.createElement("button");
        remove.className = "ghost small";
        remove.textContent = t.more.delete;
        remove.addEventListener("click", async () => {
          try {
            await api!.deleteMemory(m.id);
            await loadMemories();
          } catch (error) {
            setStatus(errorText(error), "error");
          }
        });
        const row = document.createElement("div");
        row.className = "row";
        row.append(remove);
        item.append(row);
        return item;
      }),
    );
  } catch (error) {
    setStatus(errorText(error), "error");
  }
}

async function scheduleReminder(): Promise<void> {
  const text = $<HTMLInputElement>("reminderText").value.trim();
  const when = new Date($<HTMLInputElement>("reminderAt").value);
  if (!text || Number.isNaN(when.getTime()) || when.getTime() < Date.now() + 30_000) return setStatus(t.more.reminderInvalid, "error");
  const permission = await LocalNotifications.requestPermissions();
  if (permission.display !== "granted") return setStatus(t.more.reminderDenied, "error");
  await LocalNotifications.schedule({
    notifications: [{ id: Math.floor(Date.now() / 1000) % 2_000_000_000, title: "EZO", body: text, schedule: { at: when, allowWhileIdle: true } }],
  });
  $<HTMLInputElement>("reminderText").value = "";
  setStatus(format(t.more.reminderSet, { when: when.toLocaleString(prefs.language === "uz" ? "uz-UZ" : prefs.language) }));
}

// ---------- settings and onboarding ----------
async function saveSettings(): Promise<void> {
  const url = normalizeApiUrl($<HTMLInputElement>("apiUrl").value);
  if (!url) return setStatus(t.more.urlInvalid, "error");
  prefs = { ...prefs, apiUrl: url, speakReplies: $<HTMLInputElement>("speakReplies").checked };
  savePrefs(prefs);
  const token = $<HTMLInputElement>("token").value.trim();
  if (token) await writeToken(token);
  $<HTMLInputElement>("token").value = "";
  await connect();
  try {
    const me = await api!.me();
    await refreshStatus();
    setStatus(format(t.status.connectedTo, { name: me.display_name ?? me.email ?? "EZO" }));
    showTab("chat");
  } catch (error) {
    await refreshStatus();
    setStatus(errorText(error), "error");
  }
}

let welcomeAvatar: EzoAvatar | null = null;
function showWelcome(): void {
  showTab("welcome");
  if (!welcomeAvatar && EzoAvatar.supported()) {
    welcomeAvatar = new EzoAvatar($<HTMLCanvasElement>("welcomeAvatar"), { framing: "head", terrain: false, describe: (s) => t.voice.words[s] });
    welcomeAvatar.setState("idle");
  }
}

function wire(): void {
  for (const button of document.querySelectorAll<HTMLButtonElement>("nav button")) {
    button.addEventListener("click", () => showTab(button.dataset.go ?? "chat"));
  }
  $("composer").addEventListener("submit", (event) => {
    event.preventDefault();
    const text = $<HTMLInputElement>("input").value.trim();
    if (!text) return;
    $<HTMLInputElement>("input").value = "";
    void ask(text, "text");
  });
  $("mic").addEventListener("click", () => {
    openStage();
    if (server.online) void startListening();
  });
  $("stageMic").addEventListener("click", () => void toggleStageMic());
  $("stageClose").addEventListener("click", closeStage);
  $("avatarBox").addEventListener("pointermove", (event) => {
    const rect = (event.currentTarget as HTMLElement).getBoundingClientRect();
    avatar?.setGaze({ yaw: ((event.clientX - rect.left) / rect.width) * 2 - 1, pitch: (1 - ((event.clientY - rect.top) / rect.height) * 2) * 0.6 });
  });
  for (const button of document.querySelectorAll<HTMLButtonElement>(".langs button")) {
    button.addEventListener("click", () => {
      prefs = { ...prefs, voiceLanguage: (button.dataset.lang ?? "auto") as Prefs["voiceLanguage"] };
      savePrefs(prefs);
      renderLanguage();
    });
  }
  $("camera").addEventListener("click", () => void explainPhoto());
  $("document").addEventListener("click", () => void summarizeDocument());
  $("conversation").addEventListener("change", async () => {
    const id = $<HTMLSelectElement>("conversation").value || null;
    prefs = { ...prefs, conversationId: id };
    savePrefs(prefs);
    try {
      renderMessages(id && api ? await api.messages(id) : []);
    } catch (error) {
      setStatus(errorText(error), "error");
    }
  });
  $("refresh").addEventListener("click", () => void refreshConversations());
  $("taskForm").addEventListener("submit", (event) => {
    event.preventDefault();
    void createTask();
  });
  $("ieltsBegin").addEventListener("click", () => void beginIelts());
  $("ieltsForm").addEventListener("submit", (event) => {
    event.preventDefault();
    void submitIelts();
  });
  $("ieltsMic").addEventListener("click", () => void ieltsMic());
  $("ieltsNew").addEventListener("click", () => {
    $("ieltsRun").hidden = true;
    $("ieltsStart").hidden = false;
    void loadIelts();
  });
  $("addProject").addEventListener("submit", async (event) => {
    event.preventDefault();
    const name = $<HTMLInputElement>("projectName").value.trim();
    if (!name || !api) return;
    try {
      const project = await api.createProject(name);
      $<HTMLInputElement>("projectName").value = "";
      chooseProject(project.id);
    } catch (error) {
      setStatus(errorText(error), "error");
    }
  });
  $("addMemory").addEventListener("submit", async (event) => {
    event.preventDefault();
    const content = $<HTMLInputElement>("memoryInput").value.trim();
    if (!content || !api) return;
    try {
      await api.addMemory(content);
      $<HTMLInputElement>("memoryInput").value = "";
      await loadMemories();
    } catch (error) {
      setStatus(errorText(error), "error");
    }
  });
  $("reminder").addEventListener("submit", (event) => {
    event.preventDefault();
    void scheduleReminder();
  });
  $("saveSettings").addEventListener("click", () => void saveSettings());
  $("clearToken").addEventListener("click", async () => {
    await writeToken(null);
    await connect();
    renderMessages([]);
    await refreshStatus();
    setStatus(t.status.tokenCleared);
  });
  $<HTMLSelectElement>("language").addEventListener("change", (event) => setLanguage((event.target as HTMLSelectElement).value as Lang));
  $<HTMLSelectElement>("welcomeLanguage").addEventListener("change", (event) => setLanguage((event.target as HTMLSelectElement).value as Lang));
  $("welcomeStart").addEventListener("click", () => {
    prefs = { ...prefs, onboarded: true };
    savePrefs(prefs);
    welcomeAvatar?.destroy();
    welcomeAvatar = null;
    showTab(prefs.apiUrl ? "chat" : "more");
    if (!prefs.apiUrl) setStatus(t.status.enterServer);
  });
  $("showWelcome").addEventListener("click", showWelcome);
  document.addEventListener("visibilitychange", () => {
    // Coming back to the app shows what was said on the desktop in the meantime.
    if (!document.hidden && !$("chatTab").hidden) void refreshConversations();
  });
}

async function start(): Promise<void> {
  wire();
  applyStrings();
  $<HTMLInputElement>("apiUrl").value = prefs.apiUrl;
  $<HTMLInputElement>("speakReplies").checked = prefs.speakReplies;
  if (!prefs.onboarded) return showWelcome();
  if (await connect()) {
    showTab("chat");
    void refreshStatus();
  } else {
    showTab("more");
    setStatus(t.status.enterServer);
  }
}

void start();
