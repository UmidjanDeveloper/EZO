import { chromium, expect, test, type BrowserContext } from "@playwright/test";
import { createHash, generateKeyPairSync } from "node:crypto";
import { cpSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { pathToFileURL } from "node:url";

// Loads the REAL unpacked extension in Chromium. A throwaway `key` is injected into a temp COPY of the
// manifest only to get a deterministic extension id; the shipped manifest is untouched.

const EXTENSION_SRC = path.resolve(__dirname, "../../../apps/chrome-extension");

// Only referenced inside page.evaluate(), where it runs in the extension page.
declare const chrome: {
  runtime: { getManifest(): unknown };
  permissions: { getAll(): Promise<{ permissions?: string[]; origins?: string[] }> };
};


test.describe.configure({ mode: "serial" });

let context: BrowserContext;
let extensionId = "";
let workDir = "";

test.beforeAll(async () => {
  workDir = mkdtempSync(path.join(os.tmpdir(), "ezo-ext-"));
  const extDir = path.join(workDir, "ext");
  mkdirSync(extDir);
  cpSync(EXTENSION_SRC, extDir, { recursive: true });
  const { publicKey } = generateKeyPairSync("rsa", { modulusLength: 2048 });
  const der = publicKey.export({ type: "spki", format: "der" });
  const manifestPath = path.join(extDir, "manifest.json");
  const manifest = JSON.parse(readFileSync(manifestPath, "utf8"));
  manifest.key = der.toString("base64");
  writeFileSync(manifestPath, JSON.stringify(manifest));
  extensionId = [...createHash("sha256").update(der).digest("hex").slice(0, 32)]
    .map((c) => String.fromCharCode("a".charCodeAt(0) + parseInt(c, 16)))
    .join("");

  context = await chromium.launchPersistentContext(path.join(workDir, "profile"), {
    channel: "chromium",
    headless: true,
    args: [`--disable-extensions-except=${extDir}`, `--load-extension=${extDir}`],
    ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE } : {}),
  });
});

test.afterAll(async () => {
  await context?.close();
  if (workDir) rmSync(workDir, { recursive: true, force: true });
});

test("extension: loads with scoped permissions, no content scripts, no worker, no granted host access", async () => {
  const page = await context.newPage();
  await page.goto(`chrome-extension://${extensionId}/popup.html`);
  await expect(page.getByRole("heading", { level: 1 })).toContainText("EZO OS");

  const runtime = await page.evaluate(async () => {
    const manifest = chrome.runtime.getManifest() as unknown as Record<string, unknown>;
    const granted = await chrome.permissions.getAll();
    return {
      contentScripts: manifest.content_scripts ?? null,
      background: manifest.background ?? null,
      permissions: [...(granted.permissions ?? [])].sort(),
      origins: granted.origins ?? [],
    };
  });
  expect(runtime.contentScripts).toBeNull();
  expect(runtime.background).toBeNull();
  expect(runtime.permissions).toEqual(["activeTab", "scripting", "storage"]);
  expect(runtime.origins).toEqual([]); // nothing granted until the user clicks
  expect(context.serviceWorkers()).toHaveLength(0);
});

test("extension: shows honest not-available states and makes no network call on load", async () => {
  const page = await context.newPage();
  const requests: string[] = [];
  page.on("request", (request) => {
    if (!request.url().startsWith("chrome-extension://")) requests.push(request.url());
  });
  await page.goto(`chrome-extension://${extensionId}/popup.html`);

  await expect(page.locator("#backendState")).toContainText("noma'lum");
  await expect(page.locator("#backendState")).toHaveAttribute("data-state", "unknown");
  await expect(page.locator("#pairingState")).toContainText("mavjud emas");
  await expect(page.locator("#taskState")).toContainText("mavjud emas");
  await expect(page.locator("#telegramState")).toContainText("hech narsa yuborilmaydi");

  const text = (await page.locator("body").innerText()).toLowerCase();
  for (const forbidden of ["ulangan (online)", "paired", "juftlangan", "yetkazildi", "completed"]) {
    expect(text).not.toContain(forbidden);
  }
  // No task command box exists; nothing can be sent before a preview.
  await expect(page.locator("textarea, #cancelTaskBtn, #sendCmdBtn")).toHaveCount(0);
  await expect(page.locator("#sendBtn")).toBeHidden();
  await expect(page.getByRole("button", { name: "Sahifani qisqacha bayon qil" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Tanlangan matnni tushuntir" })).toBeVisible();
  await page.waitForTimeout(3500); // the old popup polled every 3s; the new one must not
  expect(requests).toEqual([]);
});

test("extension: page reading is user-initiated and fails closed on pages it was not granted", async () => {
  const page = await context.newPage();
  await page.goto(`chrome-extension://${extensionId}/popup.html`);
  await expect(page.locator("#pageState")).toHaveText(""); // nothing read until the click
  await page.locator("#readPageBtn").click();
  await expect(page.locator("#pageState")).toContainText("o'qib bo'lmadi");
});

test("extension: summary/explanation read nothing without a granted tab and send nothing", async () => {
  const page = await context.newPage();
  const requests: string[] = [];
  page.on("request", (request) => {
    if (!request.url().startsWith("chrome-extension://")) requests.push(request.url());
  });
  await page.goto(`chrome-extension://${extensionId}/popup.html`);
  // Opened as a tab (not from the toolbar), activeTab grants nothing: reading fails closed.
  await page.getByRole("button", { name: "Sahifani qisqacha bayon qil" }).click();
  await expect(page.locator("#preview")).toContainText("o'qib bo'lmadi");
  await expect(page.locator("#sendBtn")).toBeHidden();
  // Form filling fails closed the same way and offers nothing to send or write.
  await page.locator("#readFormBtn").click();
  await expect(page.locator("#formPreview")).toContainText("o'qib bo'lmadi");
  await expect(page.locator("#askFillBtn")).toBeHidden();
  await expect(page.locator("#applyFillBtn")).toBeHidden();
  // Only loopback EZO servers can be configured.
  await page.fill("#apiBase", "https://evil.example");
  await page.click("#saveServer");
  await expect(page.locator("#answer")).toContainText("localhost");
  expect(requests).toEqual([]);
});

test("extension: form filling reads labels only, skips secrets, types approved values and never submits", async () => {
  // The extension ships plain ES modules without a package.json; import a .mjs copy in Node.
  const copy = path.join(workDir, "forms.mjs");
  cpSync(path.join(EXTENSION_SRC, "forms.js"), copy);
  type ReadForm = { fields: { id: string; label: string }[]; skippedSensitive: number };
  type Item = { id: string; index: number; fingerprint: string; value: string };
  const forms = (await import(/* @vite-ignore */ pathToFileURL(copy).href)) as {
    collectFormFields: () => ReadForm;
    fillFormFields: (items: Item[]) => { filled: number; changed: string[] };
    buildFormRequest: (form: ReadForm, instruction: string) => { message: string };
    parseFillReply: (reply: string, form: ReadForm) => { values: Item[]; rejected: { id: string }[] };
  };
  const page = await context.newPage();
  await page.setContent(`
    <form id="f" onsubmit="window.submitted = true; return false;">
      <label for="name">To'liq ism</label><input id="name" name="name" value="oldin-yozilgan-maxfiy">
      <label for="email">Email</label><input id="email" name="email" type="email">
      <label for="pw">Parol</label><input id="pw" name="pw" type="password">
      <label for="cc">Raqam</label><input id="cc" name="num" autocomplete="cc-number">
      <input type="hidden" name="csrf" value="tok">
      <label for="city">Shahar</label>
      <select id="city" name="city"><option value="">—</option><option value="tas">Toshkent</option><option value="sam">Samarqand</option></select>
      <label for="about">O'zingiz haqingizda</label><textarea id="about" name="about"></textarea>
      <button type="submit">Yuborish</button>
    </form>`);
  await page.evaluate(() => {
    (window as unknown as { inputs: number }).inputs = 0;
    document.addEventListener("input", () => (window as unknown as { inputs: number }).inputs++, true);
  });
  const read = await page.evaluate(forms.collectFormFields);
  expect(read.fields.map((f) => f.label)).toEqual(["To'liq ism", "Email", "Shahar", "O'zingiz haqingizda"]);
  expect(read.skippedSensitive).toBe(2);
  expect(JSON.stringify(read)).not.toContain("oldin-yozilgan-maxfiy"); // typed values are never read
  expect(JSON.stringify(read)).not.toContain("tok");

  const request = forms.buildFormRequest(read, "Ismim Dilnoza Karimova, email dilnoza@example.com, Samarqandda yashayman");
  expect(request.message).not.toContain("oldin-yozilgan-maxfiy");
  // What a model might answer, including a field it must not touch.
  const parsed = forms.parseFillReply(
    '{"f1": "Dilnoza Karimova", "f2": "dilnoza@example.com", "f3": "Samarqand", "f4": "Talaba", "pw": "hunter2"}',
    read,
  );
  expect(parsed.rejected.map((r) => r.id)).toEqual(["pw"]);
  const chosen = parsed.values.filter((v) => v.id !== "f4"); // the user unticks one
  const result = await page.evaluate(forms.fillFormFields, chosen);
  expect(result).toEqual({ filled: 3, changed: [] });
  expect(await page.inputValue("#name")).toBe("Dilnoza Karimova");
  expect(await page.inputValue("#email")).toBe("dilnoza@example.com");
  expect(await page.inputValue("#city")).toBe("sam");
  expect(await page.inputValue("#about")).toBe("");
  expect(await page.inputValue("#pw")).toBe("");
  expect(await page.inputValue("#cc")).toBe("");
  expect(await page.evaluate(() => (window as unknown as { inputs: number }).inputs)).toBe(3);
  expect(await page.evaluate(() => (window as unknown as { submitted?: boolean }).submitted ?? false)).toBe(false);

  // If the page changed since it was read, that field is not written.
  await page.evaluate(() => document.getElementById("email")!.setAttribute("name", "other"));
  const again = await page.evaluate(forms.fillFormFields, parsed.values);
  expect(again.changed).toContain("f2");
});
