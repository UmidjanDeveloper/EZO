import "./styles.css";
import { Camera, CameraResultType, CameraSource } from "@capacitor/camera";
import { LocalNotifications } from "@capacitor/local-notifications";
import { FilePicker } from "@capawesome/capacitor-file-picker";
import { createLevelMeter, EzoAvatar, type AvatarState, type LevelMeter } from "@ezo/avatar";
import { ApiError, createApi, type Api, type Lang, type Message } from "./api";
import { base64Bytes, documentPrompt, isStudentDocument, jobMessage, MAX_STUDENT_BYTES } from "./documents";
import { Recorder } from "./recorder";
import { loadPrefs, normalizeApiUrl, readToken, savePrefs, writeToken, type Prefs } from "./store";

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
let prefs: Prefs = loadPrefs();
let api: Api | null = null;
const recorder = new Recorder();
let player: HTMLAudioElement | null = null;

function errorText(error: unknown): string {
  return error instanceof ApiError ? error.message : `Xatolik: ${(error as Error).message ?? String(error)}`;
}

function setStatus(text: string, kind: "info" | "busy" | "error" = "info"): void {
  const status = $("status");
  status.textContent = text;
  status.className = `status ${kind}`;
}

async function connect(): Promise<boolean> {
  if (!prefs.apiUrl) return false;
  api = createApi(prefs.apiUrl, await readToken());
  return true;
}

// ---------- tabs ----------
function showTab(name: string): void {
  for (const tab of document.querySelectorAll<HTMLElement>("[data-tab]")) tab.hidden = tab.dataset.tab !== name;
  for (const button of document.querySelectorAll<HTMLButtonElement>("nav button")) {
    button.classList.toggle("active", button.dataset.go === name);
  }
  if (name === "chat") void refreshConversations();
  if (name === "projects") void loadProjects();
  if (name === "memory") void loadMemories();
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

function appendMessage(role: "user" | "assistant", content: string): void {
  const bubble = document.createElement("div");
  bubble.className = `bubble ${role}`;
  bubble.textContent = content;
  $("messages").append(bubble);
  $("messages").scrollTop = $("messages").scrollHeight;
}

async function refreshConversations(): Promise<void> {
  if (!api) return;
  try {
    const conversations = await api.conversations();
    const select = $<HTMLSelectElement>("conversation");
    const fresh = document.createElement("option");
    fresh.value = "";
    fresh.textContent = "＋ Yangi suhbat";
    select.replaceChildren(
      fresh,
      ...conversations.map((c) => {
        const option = document.createElement("option");
        option.value = c.id;
        option.textContent = c.title || "Suhbat";
        return option;
      }),
    );
    select.value = prefs.conversationId ?? "";
    if (prefs.conversationId) renderMessages(await api.messages(prefs.conversationId));
    else renderMessages([]);
    setStatus("Ulandi");
  } catch (error) {
    setStatus(errorText(error), "error");
  }
}

// --- voice stage: EZO's humanoid, full screen ------------------------------------------------

let avatar: EzoAvatar | null = null;
let meter: LevelMeter | null = null;
let meterFrame = 0;
let voiceBusy = false;

function stageState(state: AvatarState, status: string): void {
  avatar?.setState(state);
  $("stageStatus").textContent = status;
  $("stageMic").textContent = state === "listening" ? "■" : "🎤";
  $("stageMic").setAttribute("aria-label", state === "listening" ? "Tugatish" : "Gapirish");
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
  avatar ??= new EzoAvatar($<HTMLCanvasElement>("avatar"), { framing: "bust" });
  renderLanguage();
  stageState("idle", "Gapirish uchun 🎤 bosing");
}

function closeStage(): void {
  if (recorder.active) void recorder.stop();
  player?.pause();
  followLevel(null);
  avatar?.destroy(); // frees the GPU while the stage is closed
  avatar = null;
  $("voiceStage").hidden = true;
}

/** Plays EZO's reply in the reply's language; resolves when it has finished. */
async function speak(text: string, language: Lang | null): Promise<void> {
  if (!api || !prefs.speakReplies) return;
  try {
    const audio = await api.speak(text, language);
    player?.pause();
    const current = new Audio(URL.createObjectURL(audio));
    player = current;
    await new Promise<void>((resolve) => {
      current.onplaying = () => followLevel(current);
      current.onended = current.onpause = current.onerror = () => resolve();
      current.play().catch(() => resolve());
    });
  } catch (error) {
    setStatus(`Javob matnda. ${errorText(error)}`, "error");
  } finally {
    followLevel(null);
  }
}

async function ask(text: string, channel: "text" | "voice", heard: Lang | null = null): Promise<{ content: string; language: Lang | null } | null> {
  if (!api) {
    setStatus("Avval Sozlamalarda serverni kiriting.", "error");
    return null;
  }
  appendMessage("user", text);
  setStatus("EZO o‘ylayapti…", "busy");
  try {
    const { conversationId, reply, language } = await api.chat(text, prefs.conversationId, prefs.projectId, channel, heard);
    if (prefs.conversationId !== conversationId) {
      prefs = { ...prefs, conversationId };
      savePrefs(prefs);
    }
    appendMessage("assistant", reply.content);
    setStatus("Tayyor");
    return { content: reply.content, language: language ?? heard };
  } catch (error) {
    setStatus(errorText(error), "error");
    return null;
  }
}

async function startListening(): Promise<void> {
  player?.pause();
  try {
    await recorder.start();
  } catch {
    stageState("error", "Mikrofonga ruxsat berilmadi (Android sozlamalari → Ilovalar → EZO → Ruxsatlar).");
    return;
  }
  followLevel(recorder.liveStream);
  $("stageHeard").textContent = "";
  stageState("listening", "Tinglayapman… tugatgach ■ ni bosing");
}

async function finishListening(): Promise<void> {
  if (!api || voiceBusy) return;
  voiceBusy = true;
  followLevel(null);
  try {
    const audio = await recorder.stop();
    if (!audio) return stageState("idle", "Hech narsa yozilmadi. Qaytadan 🎤 bosing.");
    stageState("thinking", "Eshitganimni matnga aylantiryapman…");
    const fixed = prefs.voiceLanguage === "auto" ? null : prefs.voiceLanguage;
    const { text, language } = await api.transcribe(audio, fixed);
    if (!text) return stageState("idle", "Hech narsa eshitilmadi. Qaytadan gapiring.");
    $("stageHeard").textContent = text;
    stageState("thinking", "O‘ylayapman…");
    const reply = await ask(text, "voice", language);
    if (!reply) return stageState("error", $("status").textContent ?? "Xatolik");
    $("stageReply").textContent = reply.content;
    stageState("speaking", "Gapiryapman… (bo‘lish uchun 🎤)");
    await speak(reply.content, reply.language);
    if (!$("voiceStage").hidden && !recorder.active) stageState("idle", "Yana gapirish uchun 🎤 bosing");
  } catch (error) {
    stageState("error", errorText(error));
  } finally {
    voiceBusy = false;
  }
}

async function toggleStageMic(): Promise<void> {
  if (recorder.active) return finishListening();
  if (voiceBusy && !player?.paused) player?.pause(); // interrupt EZO and talk
  if (!voiceBusy || player?.paused) await startListening();
}

async function explainPhoto(): Promise<void> {
  if (!api) return;
  try {
    const photo = await Camera.getPhoto({
      source: CameraSource.Prompt,
      resultType: CameraResultType.Base64,
      quality: 70,
      width: 1600,
      correctOrientation: true,
      promptLabelHeader: "Rasm",
      promptLabelPhoto: "Galereyadan tanlash",
      promptLabelPicture: "Suratga olish",
    });
    if (!photo.base64String) return;
    const bytes = Uint8Array.from(atob(photo.base64String), (c) => c.charCodeAt(0));
    const mime = photo.format === "png" ? "image/png" : "image/jpeg";
    const question = $<HTMLInputElement>("input").value.trim() || "Bu rasmda nima bor? Qisqa tushuntiring.";
    $<HTMLInputElement>("input").value = "";
    appendMessage("user", `📷 ${question}`);
    setStatus("Rasm tahlil qilinmoqda…", "busy");
    const answer = await api.describeImage(new Blob([bytes], { type: mime }), question);
    appendMessage("assistant", answer);
    setStatus("Tayyor (rasm saqlanmadi)");
    await speak(answer, "uz");
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
    if (result.truncated) setStatus("Hujjat uzun: faqat boshi yuborildi.", "info");
    const reply = await ask(result.prompt, "voice");
    if (reply) await speak(reply.content, reply.language);
  } catch (error) {
    if ((error as Error).message?.toLowerCase().includes("cancel")) return;
    setStatus(errorText(error), "error");
  }
}

/** PDF/DOCX/EPUB/scans: upload to EZO Student, follow the real job, then a cited summary. */
async function readWithStudent(name: string, base64: string | undefined): Promise<void> {
  if (!api) return setStatus("Avval EZO serveriga ulaning.", "error");
  if (!base64) return setStatus("Faylni o‘qib bo‘lmadi.", "error");
  const bytes = base64Bytes(base64);
  if (bytes.length > MAX_STUDENT_BYTES) return setStatus("Fayl 5 MB dan katta.", "error");
  let job = await api.uploadStudent(name, bytes);
  const started = Date.now();
  appendMessage("user", `📄 ${name}`);
  while (job.state === "queued" || job.state === "running") {
    const waited = Math.round((Date.now() - started) / 1000);
    setStatus(jobMessage(job.state, waited), "info");
    if (waited >= 90) return; // honest: the worker may not be running; the job stays queued
    await new Promise((resolve) => setTimeout(resolve, 3000));
    job = await api.studentJob(job.id);
  }
  setStatus(jobMessage(job.state, 0, job.error_message), job.state === "completed" ? "info" : "error");
  if (job.state !== "completed") return;
  const summary = await api.studentSummary(job.document_id);
  appendMessage("assistant", summary.text + (summary.citations ? `\n\n(${summary.citations} ta manba havolasi)` : ""));
  setStatus("");
  await speak(summary.text, "uz");
}

async function scheduleReminder(): Promise<void> {
  const text = $<HTMLInputElement>("reminderText").value.trim();
  const when = new Date($<HTMLInputElement>("reminderAt").value);
  if (!text || Number.isNaN(when.getTime()) || when.getTime() < Date.now() + 30_000) {
    return setStatus("Eslatma matnini va kelajakdagi vaqtni kiriting.", "error");
  }
  const permission = await LocalNotifications.requestPermissions();
  if (permission.display !== "granted") return setStatus("Bildirishnomalarga ruxsat berilmadi.", "error");
  await LocalNotifications.schedule({
    notifications: [{ id: Math.floor(Date.now() / 1000) % 2_000_000_000, title: "EZO eslatmasi", body: text, schedule: { at: when, allowWhileIdle: true } }],
  });
  $<HTMLInputElement>("reminderText").value = "";
  setStatus(`Eslatma qo‘yildi: ${when.toLocaleString("uz-UZ")}`);
}

// ---------- projects & memory ----------
async function loadProjects(): Promise<void> {
  if (!api) return;
  try {
    const projects = await api.projects();
    const list = $("projectList");
    const none = document.createElement("li");
    none.textContent = prefs.projectId ? "Loyihasiz ishlash" : "✓ Loyihasiz";
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
  setStatus(id ? "Loyiha tanlandi: yangi suhbat shu loyihada bo‘ladi." : "Loyihasiz rejim.");
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
        return item;
      }),
    );
  } catch (error) {
    setStatus(errorText(error), "error");
  }
}

// ---------- settings ----------
async function saveSettings(): Promise<void> {
  const url = normalizeApiUrl($<HTMLInputElement>("apiUrl").value);
  if (!url) return setStatus("Manzil https:// bilan (yoki test uchun lokal tarmoqdagi http://) bo‘lishi kerak.", "error");
  prefs = { ...prefs, apiUrl: url, speakReplies: $<HTMLInputElement>("speakReplies").checked };
  savePrefs(prefs);
  const token = $<HTMLInputElement>("token").value.trim();
  if (token) await writeToken(token);
  $<HTMLInputElement>("token").value = "";
  await connect();
  try {
    const me = await api!.me();
    setStatus(`Ulandi: ${me.display_name ?? me.email ?? "EZO"}`);
    showTab("chat");
  } catch (error) {
    setStatus(errorText(error), "error");
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
    void startListening();
  });
  $("stageMic").addEventListener("click", () => void toggleStageMic());
  $("stageClose").addEventListener("click", closeStage);
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
    renderMessages(id && api ? await api.messages(id) : []);
  });
  $("refresh").addEventListener("click", () => void refreshConversations());
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
    setStatus("Token o‘chirildi.");
  });
  document.addEventListener("visibilitychange", () => {
    // Coming back to the app shows what was said on the desktop in the meantime.
    if (!document.hidden && !$("chatTab").hidden) void refreshConversations();
  });
}

async function start(): Promise<void> {
  wire();
  $<HTMLInputElement>("apiUrl").value = prefs.apiUrl;
  $<HTMLInputElement>("speakReplies").checked = prefs.speakReplies;
  if (await connect()) showTab("chat");
  else {
    showTab("settings");
    setStatus("EZO server manzili va tokenini kiriting.");
  }
}

void start();
