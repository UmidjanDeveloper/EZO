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
  // Microphone and camera are granted up front so the voice stage and the camera button can
  // be exercised without system dialogs. The emulator's camera is a synthetic scene: this is
  // a SIMULATION of the engine running on a device, not a face/hand recognition test.
  await device.shell("pm grant uz.ezo.mobile android.permission.RECORD_AUDIO").catch(() => {});
  await device.shell("pm grant uz.ezo.mobile android.permission.CAMERA").catch(() => {});
  await device.shell("am start -W -n uz.ezo.mobile/.MainActivity");
  const webview = await device.webView({ pkg: "uz.ezo.mobile" }, { timeout: 120_000 });
  const page = await webview.page();
  step("app launched and its WebView attached", page.url());
  await device.screenshot({ path: path.join(shotsDir, "1-first-launch.png") });

  // 2. First launch shows the welcome page, then asks for the server — go through it like a user.
  await page.locator("#welcomeStart").waitFor({ state: "visible", timeout: 60_000 });
  step("welcome page shown", (await page.textContent("#welcomeTab h1")) ?? "");
  await page.click("#welcomeStart");
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

  // 8. The voice stage on the real device: the humanoid draws (WebGL in the WebView), the
  // camera control is disabled and says why, the microphone state is whatever the device
  // reports (no pretending).
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
    cameraDisabled: document.getElementById("cameraToggle")?.disabled,
    cameraText: document.getElementById("cameraPrivacy")?.textContent?.slice(0, 80),
  }));
  step("voice stage on the device", JSON.stringify(stage));
  if (stage.renderer !== "webgl" && stage.renderer !== "2d") throw new Error(`avatar renderer ${stage.renderer}`);
  // 9. The real perception engine on the device: the bundled assets must verify (button enabled),
  // the camera must open through the WebView and the worker must run inference on the emulator's
  // synthetic scene. The honest state is tracking or lost; an error is recorded, not hidden.
  await page.waitForFunction(() => !document.getElementById("cameraToggle")?.disabled, undefined, { timeout: 30_000 });
  // A timeline of the engine start on the device (state changes + the worker's own console
  // lines, seconds since the press) so a slow emulator is diagnosable from the job annotations.
  const timeline = [];
  const pressedAt = Date.now();
  const since = () => `${((Date.now() - pressedAt) / 1000).toFixed(1)}s`;
  const onConsole = (message) => {
    const text = message.text();
    if (/Graph successfully started|XNNPACK|Aborted|deadline|Vision|wasm/i.test(text)) timeline.push(`${since()} console: ${text.slice(0, 120)}`);
  };
  page.on("console", onConsole);
  await page.click("#cameraToggle");
  let last = "";
  for (let i = 0; i < 120; i++) {
    const state = await page.evaluate(() => document.getElementById("cameraState")?.dataset.camera ?? "");
    if (state !== last) {
      timeline.push(`${since()} state: ${state}`);
      last = state;
    }
    if (["tracking", "lost", "error", "denied"].includes(state)) break;
    await new Promise((r) => setTimeout(r, 1000));
  }
  await new Promise((r) => setTimeout(r, 5000));
  page.off("console", onConsole);
  step("camera engine timeline on the device (SIMULATION)", timeline.join(" | "));
  const camera = await page.evaluate(() => ({
    state: document.getElementById("cameraState")?.dataset.camera,
    text: document.getElementById("cameraState")?.textContent,
    indicator: document.getElementById("cameraIndicator")?.textContent,
    fps: document.getElementById("voiceStage")?.dataset.fps,
    inferenceMs: document.getElementById("voiceStage")?.dataset.inferenceMs,
    attention: document.getElementById("voiceStage")?.dataset.attention,
  }));
  step("camera on the device (SIMULATION: emulator scene)", JSON.stringify(camera));
  if (camera.state !== "tracking" && camera.state !== "lost") throw new Error(`camera state ${camera.state}: ${camera.text}`);
  if (!(Number(camera.fps) > 0)) throw new Error(`no inference samples on the device (fps=${camera.fps})`);
  await device.screenshot({ path: path.join(shotsDir, "5-voice-stage.png") });
  await page.click("#cameraToggle");
  await page.waitForFunction(() => document.getElementById("cameraState")?.dataset.camera === "off", undefined, { timeout: 10_000 });
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
