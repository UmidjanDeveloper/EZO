// Real Android check: the installed EZO APK on an emulator connects to a real EZO API
// (token mode, offline AI) and shows a conversation started by another client, then
// sends a message that the server stores. Drives the app's own WebView over adb.
//
// Usage: EZO_TOKEN=... EZO_API=http://127.0.0.1:8000 node android-smoke.mjs <report.json> <screenshot-dir>
import { writeFileSync } from "node:fs";
import path from "node:path";
import { _android } from "@playwright/test";

const [reportPath, shotsDir] = process.argv.slice(2);
const token = process.env.EZO_TOKEN;
const api = process.env.EZO_API ?? "http://127.0.0.1:8000";
const report = { steps: [], ok: false };
const step = (name, detail = "") => {
  report.steps.push({ name, detail, at: new Date().toISOString() });
  console.log(`✓ ${name}${detail ? `: ${detail}` : ""}`);
};

async function apiCall(route, init = {}) {
  const res = await fetch(`${api}${route}`, {
    ...init,
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json", ...(init.headers ?? {}) },
  });
  if (!res.ok) throw new Error(`${route}: HTTP ${res.status} ${await res.text()}`);
  return res.json();
}

let device;
try {
  // 1. Another client (like the desktop) starts a conversation on the server.
  const desktop = await apiCall("/api/chat", {
    method: "POST",
    body: JSON.stringify({ message: "Salom EZO, bu desktopdan yozilgan xabar." }),
  });
  step("desktop conversation created", desktop.conversation_id);

  [device] = await _android.devices();
  if (!device) throw new Error("no Android device");
  step("device", `${device.model()} ${device.serial()}`);
  await device.shell("am force-stop uz.ezo.mobile");
  await device.shell("am start -W -n uz.ezo.mobile/.MainActivity");
  const webview = await device.webView({ pkg: "uz.ezo.mobile" }, { timeout: 120_000 });
  const page = await webview.page();
  step("app launched and its WebView attached", page.url());
  await device.screenshot({ path: path.join(shotsDir, "1-first-launch.png") });

  // 2. First launch asks for the server (settings tab) — fill it like a user.
  await page.locator("#apiUrl").waitFor({ state: "visible", timeout: 60_000 });
  await page.fill("#apiUrl", "http://10.0.2.2:8000");
  await page.fill("#token", token);
  await page.click("#saveSettings");
  await page.locator('[data-tab="chat"]').waitFor({ state: "visible", timeout: 60_000 });
  step("connected to the EZO server", (await page.textContent("#status")) ?? "");
  await device.screenshot({ path: path.join(shotsDir, "2-connected.png") });

  // 3. The desktop's conversation is listed and opens with its message.
  const select = page.locator("#conversation");
  await page.waitForFunction(
    (id) => [...document.querySelectorAll("#conversation option")].some((o) => o.value === id),
    desktop.conversation_id,
    { timeout: 60_000 },
  );
  await select.selectOption(desktop.conversation_id);
  await page.getByText("bu desktopdan yozilgan xabar").first().waitFor({ timeout: 60_000 });
  step("desktop conversation visible on the phone");

  // 4. The phone continues it; the server stores the phone's message in the same thread.
  await page.fill("#input", "Telefondan javob: davom etamiz.");
  await page.press("#input", "Enter");
  const deadline = Date.now() + 60_000;
  let stored = false;
  while (Date.now() < deadline && !stored) {
    const messages = await apiCall(`/api/conversations/${desktop.conversation_id}/messages`);
    stored = messages.some((m) => m.role === "user" && m.content.includes("Telefondan javob"));
    if (!stored) await new Promise((r) => setTimeout(r, 2000));
  }
  if (!stored) throw new Error("the phone's message did not reach the server");
  step("phone message stored in the same server conversation");
  await device.screenshot({ path: path.join(shotsDir, "3-continued.png") });
  report.ok = true;
} catch (error) {
  report.error = String(error?.stack ?? error);
  console.error(report.error);
  if (device) await device.screenshot({ path: path.join(shotsDir, "failure.png") }).catch(() => {});
} finally {
  writeFileSync(reportPath, JSON.stringify(report, null, 2));
  if (device) await device.close().catch(() => {});
  process.exit(report.ok ? 0 : 1);
}
