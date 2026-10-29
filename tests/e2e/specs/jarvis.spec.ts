import { expect, test } from "@playwright/test";

const API_PORT = Number(process.env.E2E_API_PORT ?? 8100);

// Real browser against the real e2e API (offline mode, no provider credentials, no paired
// device, no Telegram configuration): nothing may appear connected, paired or delivered.

const JARVIS_API = /\/api\/jarvis\//;

test("jarvis: shows real backend capabilities as not available, never connected/paired/completed", async ({ page }) => {
  await page.goto("/jarvis");
  await expect(page.getByRole("heading", { level: 1, name: /JARVIS/ })).toBeVisible();

  const features = page.getByTestId("jarvis-features");
  for (const name of ["windows_downloads", "chrome_actions", "mobile_actions", "office_pdf", "telegram_send"]) {
    const item = features.getByTestId(`jarvis-feature-${name}`);
    await expect(item).toBeVisible();
    await expect(item).toHaveAttribute("data-state", "not_available");
  }
  await expect(features).toContainText("paired_windows_companion");
  await expect(features).toContainText("configured_telegram_integration");

  const consoleBox = page.getByTestId("jarvis-console");
  await expect(consoleBox.getByTestId("jarvis-devices")).toContainText("Hali qurilma yo‘q");
  await expect(page.getByTestId("jarvis-approval")).toHaveCount(0);

  // Prerequisite codes such as `paired_windows_companion` name what is MISSING, so scan prose only.
  const body = (
    await page.locator("main").evaluate((main) => {
      const clone = main.cloneNode(true) as HTMLElement;
      clone.querySelectorAll("code").forEach((node) => node.remove());
      return clone.textContent ?? "";
    })
  ).toLowerCase();

  for (const forbidden of ["paired", "connected", "delivered", "yetkazildi", "ulangan (", "approve", "tasdiqlash va"]) {
    expect(body, `forbidden claim "${forbidden}"`).not.toContain(forbidden);
  }
  // Without a pending device or a task awaiting approval there is nothing to confirm or send.
  await expect(page.getByRole("button", { name: /execute|approve|tasdiqlash|ruxsat beraman|yuborish|send/i })).toHaveCount(0);
});

test("jarvis: only supported canonical endpoints are ever requested", async ({ page }) => {
  const requested: string[] = [];
  page.on("request", (request) => {
    if (JARVIS_API.test(request.url())) requested.push(`${request.method()} ${new URL(request.url()).pathname}`);
  });
  await page.goto("/jarvis");
  await expect(page.getByTestId("jarvis-feature-telegram_send")).toBeVisible();
  await page.getByTestId("jarvis-previous-0").fill("100");
  await page.getByTestId("jarvis-current-0").fill("125");
  await page.getByTestId("jarvis-calculate").click();
  await expect(page.getByTestId("jarvis-result")).toBeVisible();

  const unique = [...new Set(requested)].sort();
  expect(unique).toEqual([
    "GET /api/jarvis/capabilities",
    "GET /api/jarvis/devices",
    "GET /api/jarvis/tasks",
    "GET /api/jarvis/telegram/recipients",
    "POST /api/jarvis/percentages",
  ]);
});

test("jarvis: percentage calculation returns the backend result and an honest receipt", async ({ page }) => {
  await page.goto("/jarvis");
  await page.getByTestId("jarvis-previous-0").fill("100");
  await page.getByTestId("jarvis-current-0").fill("125");
  await page.getByTestId("jarvis-calculate").click();

  await expect(page.getByTestId("jarvis-result-percent")).toHaveText("25.00");
  const receipt = page.getByTestId("jarvis-receipt");
  await expect(receipt).toContainText(/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/);
  await expect(receipt).toContainText("urinilmagan"); // external delivery: not attempted
});

test("jarvis: zero base is rejected locally and sends no request", async ({ page }) => {
  const posts: string[] = [];
  page.on("request", (request) => {
    if (request.method() === "POST" && JARVIS_API.test(request.url())) posts.push(request.url());
  });
  await page.goto("/jarvis");
  await page.getByTestId("jarvis-previous-0").fill("0");
  await page.getByTestId("jarvis-current-0").fill("5");
  await page.getByTestId("jarvis-calculate").click();
  await expect(page.getByTestId("jarvis-calc-error")).toBeVisible();
  await expect(page.getByTestId("jarvis-result")).toHaveCount(0);
  expect(posts).toEqual([]);
});

test("jarvis: backend failure shows unknown state, not a fabricated paired device", async ({ page }) => {
  await page.route("**/api/jarvis/capabilities", (route) => route.abort("connectionrefused"));
  await page.goto("/jarvis");
  await expect(page.getByTestId("jarvis-load-error")).toBeVisible();
  await expect(page.getByTestId("jarvis-features").locator("[data-testid^=jarvis-feature-]")).toHaveCount(0);
  const body = (await page.locator("main").innerText()).toLowerCase();
  expect(body).not.toContain("paired");
  expect(body).not.toContain("online");
});

test("jarvis: 401 asks for authorization instead of faking state", async ({ page }) => {
  await page.route("**/api/jarvis/capabilities", (route) =>
    route.fulfill({ status: 401, json: { detail: "Unauthorized" } }),
  );
  await page.goto("/jarvis");
  await expect(page.getByTestId("jarvis-load-error")).toContainText("avtorizatsiya");
});

test("jarvis: a malformed percentage response is not displayed as a result", async ({ page }) => {
  await page.route("**/api/jarvis/percentages", (route) => route.fulfill({ status: 200, json: { results: "ok" } }));
  await page.goto("/jarvis");
  await page.getByTestId("jarvis-previous-0").fill("100");
  await page.getByTestId("jarvis-current-0").fill("125");
  await page.getByTestId("jarvis-calculate").click();
  await expect(page.getByTestId("jarvis-calc-error")).toContainText("kutilmagan");
  await expect(page.getByTestId("jarvis-result")).toHaveCount(0);
});

test("jarvis: existing navigation is preserved and the JARVIS link still works", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("link", { name: "Xotira" })).toBeVisible();
  await page.getByRole("link", { name: "JARVIS Rejimi" }).click();
  await expect(page).toHaveURL(/\/jarvis$/);
  await expect(page.getByRole("heading", { level: 1, name: /JARVIS/ })).toBeVisible();
});

test("jarvis: a device is paired only after the owner types the code shown on the device", async ({ page, request }) => {
  const { generateKeyPairSync, randomBytes, sign } = await import("node:crypto");
  const { publicKey, privateKey } = generateKeyPairSync("ed25519");
  const spki = publicKey.export({ format: "der", type: "spki" });
  const publicHex = Buffer.from(spki.subarray(spki.length - 32)).toString("hex");
  const name = `E2E PC ${randomBytes(3).toString("hex")}`;
  const nonce = randomBytes(16).toString("hex");
  const message = "ezo-jarvis-device-pairing-v1\u0000" + JSON.stringify({ name, nonce, platform: "windows" });
  const signature = sign(null, Buffer.from(message), privateKey).toString("hex");
  const pairing = await request.post(`http://localhost:${API_PORT}/api/jarvis/devices/pairing`, {
    data: { name, platform: "windows", public_key: publicHex, nonce, signature, capabilities: ["files.latest_documents"] },
  });
  expect(pairing.status()).toBe(201);
  const { code } = (await pairing.json()) as { code: string };

  await page.goto("/jarvis");
  const devices = page.getByTestId("jarvis-devices");
  const row = devices.locator("li", { hasText: name });
  await expect(row).toContainText("tasdiq kutmoqda");
  await row.getByLabel("Qurilmadagi kod").fill(code === "000000" ? "111111" : "000000");
  await row.getByRole("button", { name: "Tasdiqlash" }).click();
  await expect(page.getByTestId("jarvis-console").getByRole("alert")).toContainText("does not match");
  await expect(row).toContainText("tasdiq kutmoqda");
  await row.getByLabel("Qurilmadagi kod").fill(code);
  await row.getByRole("button", { name: "Tasdiqlash" }).click();
  await expect(row).toContainText("ulangan");
  await row.getByRole("button", { name: "Bekor qilish" }).click();
  await expect(row).toContainText("bekor qilingan");
});
