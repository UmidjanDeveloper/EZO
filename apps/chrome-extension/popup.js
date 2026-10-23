// EZO OS JARVIS Browser Companion Popup Logic
const API_BASE = "http://localhost:8000/api/jarvis";

document.addEventListener("DOMContentLoaded", async () => {
  const currentDomainEl = document.getElementById("currentDomain");
  const togglePermBtn = document.getElementById("togglePermBtn");
  const backendStatusEl = document.getElementById("backendStatus");
  const statusTextEl = document.getElementById("statusText");
  const taskDescEl = document.getElementById("taskDesc");
  const taskStepEl = document.getElementById("taskStep");
  const taskActionsEl = document.getElementById("taskActions");
  const cancelTaskBtn = document.getElementById("cancelTaskBtn");
  const commandInputEl = document.getElementById("commandInput");
  const sendCmdBtn = document.getElementById("sendCmdBtn");

  let currentOrigin = "";
  let activeTaskId = null;

  // 1. Resolve current active tab
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (tab && tab.url) {
      const url = new URL(tab.url);
      currentOrigin = url.origin + "/*";
      currentDomainEl.textContent = url.hostname;

      // Check explicit permission
      const hasPermission = await chrome.permissions.contains({ origins: [currentOrigin] });
      updatePermissionUi(hasPermission);
    }
  } catch (err) {
    currentDomainEl.textContent = "Brauzer sahifasi";
  }

  function updatePermissionUi(hasPermission) {
    if (hasPermission) {
      togglePermBtn.textContent = "Ruxsat Berilgan";
      togglePermBtn.className = "btn";
      togglePermBtn.style.background = "#238636";
      togglePermBtn.style.color = "#fff";
      togglePermBtn.disabled = true;
    } else {
      togglePermBtn.textContent = "Ruxsat Berish";
      togglePermBtn.className = "btn btn-primary";
      togglePermBtn.disabled = false;
    }
  }

  // Permission request handler
  togglePermBtn.addEventListener("click", async () => {
    if (!currentOrigin) return;
    try {
      const granted = await chrome.permissions.request({ origins: [currentOrigin] });
      updatePermissionUi(granted);
    } catch (e) {
      console.error("Permission request failed", e);
    }
  });

  // 2. Poll backend and active task status
  async function refreshStatus() {
    try {
      const res = await fetch(`${API_BASE}/companion/status`);
      if (res.ok) {
        statusTextEl.textContent = "Ulangan (Online)";
        backendStatusEl.style.borderColor = "rgba(16, 185, 129, 0.3)";
      } else {
        throw new Error("Offline");
      }
    } catch {
      statusTextEl.textContent = "Ulanmagan (Offline)";
      backendStatusEl.style.borderColor = "rgba(248, 81, 73, 0.3)";
    }

    try {
      const tasksRes = await fetch(`${API_BASE}/tasks`);
      if (tasksRes.ok) {
        const tasks = await tasksRes.json();
        const active = tasks.find(t => t.status === "running" || t.status === "awaiting_approval");
        if (active) {
          activeTaskId = active.id;
          taskDescEl.textContent = active.instruction;
          const currentStep = active.steps.find(s => s.id === active.current_step_id) || active.steps[0];
          taskStepEl.textContent = `Qadam: ${currentStep ? (currentStep.title_uz || currentStep.title) : "Bajarilmoqda"} (${active.status})`;
          taskActionsEl.style.display = "block";
        } else {
          activeTaskId = null;
          taskDescEl.textContent = "Ayni paytda faol vazifa yo'q";
          taskStepEl.textContent = "Holat: Bo'sh (Idle)";
          taskActionsEl.style.display = "none";
        }
      }
    } catch (err) {
      console.warn("Could not fetch tasks", err);
    }
  }

  // Cancel task
  cancelTaskBtn.addEventListener("click", async () => {
    if (!activeTaskId) return;
    try {
      await fetch(`${API_BASE}/tasks/${activeTaskId}/cancel`, { method: "POST" });
      await refreshStatus();
    } catch (err) {
      console.error("Cancel failed", err);
    }
  });

  // Send command
  sendCmdBtn.addEventListener("click", async () => {
    const text = commandInputEl.value.trim();
    if (!text) return;
    try {
      sendCmdBtn.disabled = true;
      const res = await fetch(`${API_BASE}/plan`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ instruction: text, language: "uz" }),
      });
      if (res.ok) {
        const plan = await res.json();
        // Trigger execution
        await fetch(`${API_BASE}/tasks/${plan.id}/execute`, { method: "POST" });
        commandInputEl.value = "";
        await refreshStatus();
      }
    } catch (err) {
      console.error("Command execution failed", err);
    } finally {
      sendCmdBtn.disabled = false;
    }
  });

  refreshStatus();
  setInterval(refreshStatus, 3000);
});
