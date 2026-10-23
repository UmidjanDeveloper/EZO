import { expect, test } from "@playwright/test";

// Real browser against the real e2e API (offline mode, no provider credentials). The canonical
// backend has no device pairing / task / PDF / Telegram routes, so none of that may appear as available.

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

  const unavailable = page.getByTestId("jarvis-task-unavailable");
  await expect(unavailable).toContainText("Mavjud emas");

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
  // No task execution controls exist at all.
  await expect(page.getByRole("button", { name: /bajarish|execute|approve|tasdiqlash|yuborish|send/i })).toHaveCount(0);
  await expect(page.locator("textarea")).toHaveCount(0);
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
  expect(unique).toEqual(["GET /api/jarvis/capabilities", "POST /api/jarvis/percentages"]);
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
