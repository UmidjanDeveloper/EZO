import {
  CHAT_PATH,
  DEFAULT_API_BASE,
  HEALTH_PATH,
  UNAVAILABLE,
  buildRequest,
  describeBackend,
  describePage,
  describePreview,
  originPattern,
  validApiBase,
} from "./status.js";

// Everything here runs only after the user clicks. There is no polling, no background
// worker, no content script, and no call to any planning/execution/pairing endpoint.
// Page text leaves the browser only after the user saw a preview and pressed "Yuborish".

const $ = (id) => document.getElementById(id);

$("pairingState").textContent = UNAVAILABLE.pairing;
$("taskState").textContent = UNAVAILABLE.tasks;
$("telegramState").textContent = UNAVAILABLE.telegram;
let apiBase = DEFAULT_API_BASE;
$("backendBase").textContent = apiBase;

// The token lives in session storage (cleared when the browser closes) unless the owner
// explicitly chooses to remember it on this device.
async function loadServer() {
  const local = await chrome.storage.local.get(["apiBase", "token"]);
  const session = await chrome.storage.session.get(["token"]);
  apiBase = validApiBase(local.apiBase) ?? DEFAULT_API_BASE;
  $("apiBase").value = apiBase;
  $("backendBase").textContent = apiBase;
  $("rememberToken").checked = Boolean(local.token);
  return session.token || local.token || "";
}

async function currentToken() {
  const local = await chrome.storage.local.get(["token"]);
  const session = await chrome.storage.session.get(["token"]);
  return session.token || local.token || "";
}

$("saveServer").addEventListener("click", async () => {
  const base = validApiBase($("apiBase").value);
  if (!base) {
    $("answer").textContent = "Faqat http://localhost yoki http://127.0.0.1 manzili qabul qilinadi.";
    return;
  }
  apiBase = base;
  $("backendBase").textContent = base;
  const token = $("token").value.trim();
  await chrome.storage.local.set({ apiBase: base });
  if (token) {
    await chrome.storage.session.set({ token });
    if ($("rememberToken").checked) await chrome.storage.local.set({ token });
    else await chrome.storage.local.remove("token");
  } else if (!$("rememberToken").checked) {
    await chrome.storage.local.remove("token");
  }
  $("token").value = "";
  $("answer").textContent = "Saqlandi.";
});

void loadServer();

function renderBackend(result) {
  const view = describeBackend(result);
  const el = $("backendState");
  el.textContent = view.text;
  el.dataset.state = view.state;
}

renderBackend(null);

$("checkBackendBtn").addEventListener("click", async () => {
  const button = $("checkBackendBtn");
  button.disabled = true;
  try {
    // User gesture: ask for exactly this one origin, then call exactly GET /api/health.
    const granted = await chrome.permissions.request({ origins: [originPattern(apiBase)] });
    if (!granted) return renderBackend({ ok: false, reason: "permission_denied" });
    try {
      const res = await fetch(`${apiBase}${HEALTH_PATH}`, { credentials: "omit", cache: "no-store" });
      renderBackend(res.ok ? { ok: true, status: res.status } : { ok: false, reason: "http_error", status: res.status });
    } catch {
      renderBackend({ ok: false, reason: "unreachable" });
    }
  } catch {
    renderBackend({ ok: false, reason: "permission_denied" });
  } finally {
    button.disabled = false;
  }
});

$("readPageBtn").addEventListener("click", async () => {
  const out = $("pageState");
  out.textContent = "";
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab || tab.id === undefined) throw new Error("no_tab");
    // activeTab grants access to this tab only, for this gesture. Nothing persistent is injected.
    const [injection] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => ({
        ok: true,
        title: document.title,
        origin: location.origin,
        selectionLength: (window.getSelection()?.toString() ?? "").length,
      }),
    });
    const view = describePage(injection?.result);
    out.textContent = view.ok
      ? `${view.origin} — "${view.title}" — tanlangan matn: ${view.selectionLength} belgi`
      : view.text;
  } catch {
    out.textContent = describePage(null).text;
  }
});

// --- summary / explanation: click → read this tab → preview → confirm → POST /api/chat ---

let pending = null;
let controller = null;

function resetAssist() {
  pending = null;
  $("sendBtn").hidden = true;
  $("cancelBtn").hidden = true;
}

async function prepare(kind) {
  resetAssist();
  $("answer").textContent = "";
  $("preview").textContent = "";
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab || tab.id === undefined) throw new Error("no_tab");
    // activeTab: this tab only, for this click. Visible text only; no forms or cookies.
    const [injection] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => ({
        ok: true,
        title: document.title,
        origin: location.origin,
        text: (document.body?.innerText ?? "").slice(0, 20000),
        selection: (window.getSelection()?.toString() ?? "").slice(0, 8000),
      }),
    });
    const request = buildRequest(kind, injection?.result);
    if (!request) {
      $("preview").textContent = kind === "explain" ? "Avval sahifada matnni belgilang." : "Sahifada o'qiladigan matn topilmadi.";
      return;
    }
    pending = request;
    $("preview").textContent = describePreview(kind, request.preview);
    $("sendBtn").hidden = false;
    $("cancelBtn").hidden = false;
  } catch {
    $("preview").textContent = describePage(null).text;
  }
}

$("summaryBtn").addEventListener("click", () => void prepare("summary"));
$("explainBtn").addEventListener("click", () => void prepare("explain"));

$("cancelBtn").addEventListener("click", () => {
  if (controller) controller.abort();
  resetAssist();
  $("preview").textContent = "Bekor qilindi. Hech narsa yuborilmadi.";
});

$("sendBtn").addEventListener("click", async () => {
  if (!pending) return;
  const request = pending;
  $("sendBtn").hidden = true;
  $("answer").textContent = "EZO o'ylamoqda…";
  try {
    const granted = await chrome.permissions.request({ origins: [originPattern(apiBase)] });
    if (!granted) throw new Error("Ruxsat berilmadi.");
    const token = await currentToken();
    controller = new AbortController();
    const res = await fetch(`${apiBase}${CHAT_PATH}`, {
      method: "POST",
      credentials: "omit",
      cache: "no-store",
      signal: controller.signal,
      headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: JSON.stringify({ message: request.message }),
    });
    const body = await res.json().catch(() => null);
    if (!res.ok) throw new Error(body?.error?.message ?? `HTTP ${res.status}`);
    $("answer").textContent = body?.message?.content ?? "(bo'sh javob)";
    $("preview").textContent = "Javob EZO suhbatlar tarixida ham saqlandi.";
  } catch (error) {
    $("answer").textContent = error?.name === "AbortError" ? "Bekor qilindi." : `Xatolik: ${error?.message ?? error}`;
  } finally {
    controller = null;
    resetAssist();
  }
});
