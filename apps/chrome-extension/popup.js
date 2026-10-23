import { DEFAULT_API_BASE, HEALTH_PATH, UNAVAILABLE, describeBackend, describePage, originPattern } from "./status.js";

// Everything here runs only after the user clicks. There is no polling, no background
// worker, no content script, and no call to any planning/execution/pairing endpoint.

const $ = (id) => document.getElementById(id);

$("pairingState").textContent = UNAVAILABLE.pairing;
$("taskState").textContent = UNAVAILABLE.tasks;
$("telegramState").textContent = UNAVAILABLE.telegram;
$("backendBase").textContent = DEFAULT_API_BASE;

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
    const granted = await chrome.permissions.request({ origins: [originPattern(DEFAULT_API_BASE)] });
    if (!granted) return renderBackend({ ok: false, reason: "permission_denied" });
    try {
      const res = await fetch(`${DEFAULT_API_BASE}${HEALTH_PATH}`, { credentials: "omit", cache: "no-store" });
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
