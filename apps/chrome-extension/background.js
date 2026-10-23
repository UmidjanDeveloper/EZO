// EZO OS JARVIS Browser Companion - Background Service Worker

chrome.runtime.onInstalled.addListener(() => {
  console.log("EZO OS JARVIS Browser Companion installed.");
});

// Listen for messages from popup or web pages
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === "GET_DEVICE_INFO") {
    sendResponse({
      device: "Chrome Browser Extension",
      manifestVersion: 3,
      platform: navigator.platform,
    });
    return true;
  }

  if (request.action === "NOTIFY_APPROVAL_REQUIRED") {
    chrome.notifications.create({
      type: "basic",
      iconUrl: "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='%2310b981'><circle cx='12' cy='12' r='10'/></svg>",
      title: "EZO OS — Tasdiqlash Talab Qilinadi",
      message: request.message || "JARVIS topshirig'i bo'yicha ruxsat talab etilmoqda.",
      priority: 2,
    });
    sendResponse({ notified: true });
    return true;
  }
});
