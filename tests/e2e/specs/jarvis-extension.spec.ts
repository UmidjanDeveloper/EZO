import { chromium, expect, test, type BrowserContext } from "@playwright/test";
import { createHash, generateKeyPairSync } from "node:crypto";
import { cpSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";

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
  expect(runtime.permissions).toEqual(["activeTab", "scripting"]);
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
  // No task command box or cancel button exists.
  await expect(page.locator("input[type=text], textarea, #cancelTaskBtn, #sendCmdBtn")).toHaveCount(0);
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
