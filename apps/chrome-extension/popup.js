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
import { buildFormRequest, collectFormFields, describeFormPreview, fillFormFields, parseFillReply } from "./forms.js";

// Everything here runs only after the user clicks. There is no polling, no background
// worker, no content script, and no call to any planning/execution/pairing endpoint.
// Page text leaves the browser only after the user saw a preview and pressed "Yuborish".
// Form filling types only values the user ticked; it never submits or clicks anything.

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

// --- approved form filling: read labels → preview → ask EZO → review each value → type ---

let formRead = null;
let fillTabId = null;
let suggestions = [];

function resetFill(message = "") {
  formRead = null;
  fillTabId = null;
  suggestions = [];
  $("fillInstructionLabel").hidden = true;
  $("askFillBtn").hidden = true;
  $("applyFillBtn").hidden = true;
  $("cancelFillBtn").hidden = true;
  $("fillChoices").replaceChildren();
  $("fillResult").textContent = message;
}

$("readFormBtn").addEventListener("click", async () => {
  resetFill();
  $("formPreview").textContent = "";
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab || tab.id === undefined) throw new Error("no_tab");
    // activeTab: this tab only, for this click. Labels and types only, never typed values.
    const [injection] = await chrome.scripting.executeScript({ target: { tabId: tab.id }, func: collectFormFields });
    const form = injection?.result;
    if (!form?.ok || form.fields.length === 0) {
      $("formPreview").textContent = form?.ok ? "Bu sahifada to'ldiriladigan maydon topilmadi." : describePage(null).text;
      return;
    }
    formRead = form;
    fillTabId = tab.id;
    $("formPreview").textContent = describeFormPreview({
      origin: form.origin,
      count: form.fields.length,
      skipped: form.skippedSensitive,
    });
    $("fillInstructionLabel").hidden = false;
    $("askFillBtn").hidden = false;
    $("cancelFillBtn").hidden = false;
  } catch {
    $("formPreview").textContent = describePage(null).text;
  }
});

$("cancelFillBtn").addEventListener("click", () => resetFill("Bekor qilindi. Sahifaga hech narsa yozilmadi."));

$("askFillBtn").addEventListener("click", async () => {
  const request = buildFormRequest(formRead, $("fillInstruction").value);
  if (!request) {
    $("fillResult").textContent = "Avval nima yozilishini kiriting.";
    return;
  }
  $("askFillBtn").hidden = true;
  $("fillResult").textContent = "EZO o'ylamoqda…";
  try {
    const granted = await chrome.permissions.request({ origins: [originPattern(apiBase)] });
    if (!granted) throw new Error("Ruxsat berilmadi.");
    const token = await currentToken();
    const res = await fetch(`${apiBase}${CHAT_PATH}`, {
      method: "POST",
      credentials: "omit",
      cache: "no-store",
      headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: JSON.stringify({ message: request.message }),
    });
    const body = await res.json().catch(() => null);
    if (!res.ok) throw new Error(body?.error?.message ?? `HTTP ${res.status}`);
    const parsed = parseFillReply(body?.message?.content ?? "", formRead);
    suggestions = parsed.values;
    const items = parsed.values.map((v) => {
      const li = document.createElement("li");
      const label = document.createElement("label");
      const box = document.createElement("input");
      box.type = "checkbox";
      box.checked = true;
      box.dataset.id = v.id;
      label.append(box, ` ${v.label}: `);
      const value = document.createElement("strong");
      value.textContent = v.value; // shown as text, never as HTML
      label.append(value);
      li.append(label);
      return li;
    });
    $("fillChoices").replaceChildren(...items);
    const rejected = parsed.rejected.length ? ` ${parsed.rejected.length} ta taklif rad etildi (noto'g'ri format).` : "";
    $("fillResult").textContent = parsed.ok ? `Tekshiring va keraklilarini belgilang.${rejected}` : `${parsed.reason}${rejected}`;
    $("applyFillBtn").hidden = !parsed.ok;
  } catch (error) {
    $("fillResult").textContent = `Xatolik: ${error?.message ?? error}`;
    $("askFillBtn").hidden = false;
  }
});

$("applyFillBtn").addEventListener("click", async () => {
  const chosen = new Set(
    [...$("fillChoices").querySelectorAll("input[type=checkbox]")].filter((b) => b.checked).map((b) => b.dataset.id),
  );
  const items = suggestions.filter((s) => chosen.has(s.id));
  if (!items.length || fillTabId === null) return resetFill("Hech narsa tanlanmadi. Sahifaga hech narsa yozilmadi.");
  try {
    const [injection] = await chrome.scripting.executeScript({
      target: { tabId: fillTabId },
      func: fillFormFields,
      args: [items],
    });
    const result = injection?.result ?? { filled: 0, changed: [] };
    const changed = result.changed.length ? ` ${result.changed.length} ta maydon sahifa o'zgargani uchun yozilmadi.` : "";
    resetFill(`${result.filled} ta maydon to'ldirildi.${changed} Forma yuborilmadi — tekshirib, o'zingiz yuboring.`);
  } catch {
    resetFill("Sahifaga yozib bo'lmadi (tab yopilgan yoki ruxsat tugagan bo'lishi mumkin).");
  }
});
