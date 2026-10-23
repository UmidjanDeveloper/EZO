// EZO OS JARVIS Browser Companion - Content Script
// Strictly permission-aware; does not silently harvest or execute unreviewed scripts.

(() => {
  // Check if current frame is top frame
  if (window.top !== window) return;

  // Listen for messages from background/popup
  chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === "GET_PAGE_METADATA") {
      sendResponse({
        title: document.title,
        url: window.location.href,
        hasSelection: Boolean(window.getSelection()?.toString()),
      });
      return true;
    }

    if (request.action === "GET_SELECTED_TEXT") {
      const selection = window.getSelection()?.toString() || "";
      sendResponse({ selection });
      return true;
    }
  });
})();
