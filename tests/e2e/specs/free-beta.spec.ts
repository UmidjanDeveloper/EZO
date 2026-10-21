import { expect, test } from "@playwright/test";

// Browser capability contract only; backend authorization/storage is separately tested.
test("free beta: truthful banner, restricted navigation and DOCX-only Office", async ({ page }) => {
  await page.route("**/api/status", async route => {
    const response = await route.fetch();
    await route.fulfill({ json: { ...(await response.json()), deployment_profile: "free-beta" } });
  });
  await page.goto("/office");
  await expect(page.getByRole("status").filter({ hasText: "Bepul beta" })).toBeVisible();
  await expect(page.locator('nav a[href="/student"]')).toHaveCount(0);
  const pdf = page.getByRole("checkbox");
  await expect(pdf).toBeDisabled();
  await expect(pdf).not.toBeChecked();
});


test("Office download sends owner token in header and never in the URL", async ({ page }) => {
  const token = "non-secret-browser-download-fixture";
  await page.addInitScript(value => localStorage.setItem("ezo-api-token", value), token);
  await page.route("**/api/status", async route => {
    const response = await route.fetch();
    await route.fulfill({ json: { ...(await response.json()), deployment_profile: "free-beta" } });
  });
  let authenticated = false;
  await page.route("**/api/artifacts/*/versions/*/download", async route => {
    expect(route.request().headers()["authorization"]).toBe(`Bearer ${token}`);
    expect(new URL(route.request().url()).search).toBe("");
    authenticated = true;
    await route.continue();
  });
  await page.goto("/office");
  await expect(page.getByRole("status").filter({ hasText: "Bepul beta" })).toBeVisible();
  await page.getByRole("button", { name: "Hujjatni shakllantirish", exact: true }).click();
  const downloaded = page.waitForEvent("download");
  await page.getByRole("button", { name: "DOCX yuklab olish", exact: true }).click();
  expect((await downloaded).suggestedFilename()).toMatch(/\.docx$/);
  expect(authenticated).toBeTruthy();
});
