import { expect, test } from "@playwright/test";

test("mobile: navigation drawer and chat work on a phone", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("composer-input")).toBeVisible();
  await page.getByRole("button", { name: "Menyu" }).click();
  await page.getByRole("link", { name: "Xotira" }).click();
  await expect(page.getByRole("heading", { name: "Xotira" })).toBeVisible();
});
