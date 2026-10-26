import { expect, test } from "@playwright/test";

// F26: the Admin, JARVIS and Student pages used to be Uzbek-only. With the UI language
// set to English (the same setting the Settings page writes), their words must change.

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("ezo-ui-language", "en"));
});

test("i18n: the Student page speaks English when the UI language is English", async ({ page }) => {
  await page.goto("/student");
  await expect(page.getByRole("heading", { name: "EZO Student" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Save text", exact: true })).toBeVisible();
  await expect(page.getByText("No AI provider is connected.", { exact: false })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.lang)).toBe("en");
});

test("i18n: the JARVIS console and the Admin page speak English too", async ({ page }) => {
  await page.goto("/jarvis");
  await expect(page.getByTestId("jarvis-devices")).toContainText("No devices yet.");
  await page.route("**/api/admin/governance/status", (route) =>
    route.fulfill({ status: 403, json: { error: { code: "forbidden", message: "Super Admin privileges required." } } }),
  );
  await page.goto("/admin");
  await expect(page.getByText("Access denied (403 Forbidden)")).toBeVisible();
});
