import { expect, test } from "@playwright/test";

test("mobile: history drawer and chat work on a phone", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("main").getByTestId("ezo-robot")).toBeVisible();
  await expect(page.getByTestId("composer-input")).toBeVisible();
  await page.getByTestId("open-history").click();
  await page.getByRole("link", { name: "Xotira" }).click();
  await expect(page.getByRole("heading", { level: 1, name: /Xotira/ })).toBeVisible();
});

test("mobile: Student upload and reading controls fit the phone", async ({ page }) => {
  await page.goto("/student");
  await expect(page.getByRole("heading", { name: "EZO Student" })).toBeVisible();
  await expect(page.getByLabel("Yoki o‘rganish uchun matn")).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
});
