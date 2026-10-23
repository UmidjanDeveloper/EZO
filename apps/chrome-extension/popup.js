// EZO OS JARVIS status popup.
// Calls only GET /api/jarvis/capabilities with the owner's bearer token and shows the
// real answer. It reads no page content and sends no commands: the backend has no
// task/plan/device endpoints yet, so nothing here pretends to run one.
"use strict";

const apiUrlInput = document.getElementById("apiUrl");
const tokenInput = document.getElementById("token");
const statusEl = document.getElementById("status");
const featuresEl = document.getElementById("features");

function show(text) {
  statusEl.textContent = text;
}

function normalize(url) {
  const parsed = new URL(url);
  const local = parsed.hostname === "localhost" || parsed.hostname === "127.0.0.1";
  if (parsed.protocol !== "https:" && !(local && parsed.protocol === "http:")) {
    throw new Error("Faqat https (yoki localhost) manzil qabul qilinadi.");
  }
  return parsed.origin;
}

async function check() {
  featuresEl.textContent = "";
  const { apiUrl, token } = await chrome.storage.local.get(["apiUrl", "token"]);
  if (!apiUrl) {
    show("API manzili kiritilmagan.");
    return;
  }
  show("Tekshirilmoqda…");
  let response;
  try {
    response = await fetch(`${apiUrl}/api/jarvis/capabilities`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
  } catch {
    show("API’ga ulanib bo‘lmadi (tarmoq yoki CORS: kengaytma manzilini EZO_CORS_ORIGINS’ga qo‘shing).");
    return;
  }
  if (response.status === 401) {
    show("Token noto‘g‘ri yoki kiritilmagan (401).");
    return;
  }
  if (!response.ok) {
    show(`API xatosi: ${response.status}`);
    return;
  }
  const data = await response.json();
  show("Ulandi. Qurilma amallari holati:");
  for (const [name, state] of Object.entries(data.device_features || {})) {
    const li = document.createElement("li");
    li.textContent = state.available
      ? `${name}: mavjud`
      : `${name}: mavjud emas (kerak: ${state.missing_prerequisites.join(", ")})`;
    featuresEl.appendChild(li);
  }
}

document.getElementById("save").addEventListener("click", async () => {
  try {
    const apiUrl = normalize(apiUrlInput.value.trim());
    await chrome.storage.local.set({ apiUrl, token: tokenInput.value.trim() });
    tokenInput.value = "";
    await check();
  } catch (error) {
    show(error.message);
  }
});

chrome.storage.local.get(["apiUrl"]).then(({ apiUrl }) => {
  if (apiUrl) apiUrlInput.value = apiUrl;
  void check();
});
