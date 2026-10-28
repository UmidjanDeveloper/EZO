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
  // The microphone is granted up front so the voice stage opens without a system dialog.
  // The app has no camera permission at all (EZO does not use camera tracking).
  await device.shell("pm grant uz.ezo.mobile android.permission.RECORD_AUDIO").catch(() => {});
  await device.shell("am start -W -n uz.ezo.mobile/.MainActivity");
  const webview = await device.webView({ pkg: "uz.ezo.mobile" }, { timeout: 120_000 });
  const page = await webview.page();
  step("app launched and its WebView attached", page.url());
  await device.screenshot({ path: path.join(shotsDir, "1-first-launch.png") });

  // 2. First launch shows the welcome page, then asks for the server — go through it like a user.
  await page.locator("#welcomeStart").waitFor({ state: "visible", timeout: 60_000 });
  step("welcome page shown", (await page.textContent("#welcomeTab h1")) ?? "");
  // The WebView sometimes reports a button below the fold as "outside of the viewport" even
  // after scrolling (seen once on the CI emulator at d97cad7); a real tap is tried first and
  // the fallback is the element's own click handler, recorded as such.
  try {
    await page.click("#welcomeStart", { timeout: 10_000 });
  } catch (error) {
    step("welcome button: real tap refused by the WebView viewport, clicked through the DOM", String(error).split("\n")[0].slice(0, 160));
    await page.evaluate(() => document.getElementById("welcomeStart")?.click());
  }
  await page.locator("#apiUrl").waitFor({ state: "visible", timeout: 60_000 });
  await page.fill("#apiUrl", "http://10.0.2.2:8000");
  await page.fill("#token", token);
  await page.click("#saveSettings");
  await page.locator('[data-tab="chat"]').waitFor({ state: "visible", timeout: 60_000 });
  step("connected to the EZO server", (await page.textContent("#status")) ?? "");
  await device.screenshot({ path: path.join(shotsDir, "2-connected.png") });

  // 3. The desktop's conversation is listed and opens with its message.
  const phoneState = () =>
    page.evaluate(() => ({
      chatHidden: document.getElementById("chatTab")?.hidden,
      status: document.getElementById("status")?.textContent,
      selected: document.querySelector("#conversation")?.value,
      options: [...document.querySelectorAll("#conversation option")].map((o) => o.value).slice(0, 5),
      bubbles: [...document.querySelectorAll("#messages .bubble")].map((b) => b.textContent?.slice(0, 60)),
    }));
  try {
    await page.waitForFunction(
      (id) => [...document.querySelectorAll("#conversation option")].some((o) => o.value === id),
      desktop.conversation_id,
      { timeout: 60_000 },
    );
    step("desktop conversation listed on the phone");
    await page.locator("#conversation").selectOption(desktop.conversation_id);
    await page.waitForFunction(
      () =>
        [...document.querySelectorAll("#messages .bubble")].some((b) =>
          b.textContent?.includes("bu desktopdan yozilgan xabar"),
        ),
      undefined,
      { timeout: 60_000 },
    );
  } catch (error) {
    throw new Error(`${String(error).split("\n")[0]} | phone state: ${JSON.stringify(await phoneState())}`);
  }
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

  // 5. The other screens render against the real server: tasks, IELTS, files, and English words.
  await page.click('nav button[data-go="tasks"]');
  await page.locator("#taskList li").first().waitFor({ timeout: 30_000 });
  step("tasks screen", (await page.textContent("#taskCapabilities"))?.slice(0, 160) ?? "");
  await page.click('nav button[data-go="learn"]');
  await page.waitForFunction(() => document.querySelectorAll("#cueCard option").length > 1, undefined, { timeout: 30_000 });
  step("IELTS cue cards loaded", String(await page.locator("#cueCard option").count()));
  await page.click('nav button[data-go="files"]');
  await page.locator("#fileList li").first().waitFor({ timeout: 30_000 });
  step("files screen", (await page.textContent("#fileList li")) ?? "");
  await page.click('nav button[data-go="more"]');
  await page.selectOption("#language", "en");
  await page.waitForFunction(() => document.querySelector('nav button[data-go="chat"]')?.textContent === "Chat", undefined, { timeout: 10_000 });
  step("language switched to English", (await page.getAttribute("#dot", "aria-label")) ?? "");
  await device.screenshot({ path: path.join(shotsDir, "4-english.png") });

  // 8. The voice stage on the real device: the humanoid draws (WebGL in the WebView), there is
  // no camera on the stage, the microphone state is whatever the device reports (no pretending).
  await page.click('nav button[data-go="chat"]');
  await page.click("#mic");
  await page.locator("#voiceStage").waitFor({ state: "visible", timeout: 30_000 });
  await page.waitForFunction(() => document.getElementById("avatar")?.dataset.ezoAvatar !== undefined, undefined, { timeout: 30_000 });
  const stage = await page.evaluate(() => ({
    renderer: document.getElementById("avatar")?.dataset.ezoAvatar,
    points: document.getElementById("avatar")?.dataset.points,
    power: document.getElementById("avatar")?.dataset.power,
    state: document.getElementById("avatar")?.dataset.state,
    status: document.getElementById("stageStatus")?.textContent,
    camera: Boolean(document.getElementById("cameraToggle")),
    video: document.querySelectorAll("video").length,
  }));
  step("voice stage on the device", JSON.stringify(stage));
  if (stage.renderer !== "webgl" && stage.renderer !== "2d") throw new Error(`avatar renderer ${stage.renderer}`);
  if (stage.camera || stage.video) throw new Error("the voice stage must not contain a camera");
  await device.screenshot({ path: path.join(shotsDir, "5-voice-stage.png") });
  await page.click("#stageClose");
  await page.locator("#voiceStage").waitFor({ state: "hidden", timeout: 10_000 });
  step("voice stage closed; figure and any media released");
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
