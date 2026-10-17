import { expect, test } from "@playwright/test";

test("settings: system status and interface language", async ({ page }) => {
  await page.goto("/settings");
  const status = page.getByTestId("system-status");
  await expect(status).toContainText("Anthropic Claude");
  await expect(status).toContainText("Ulanmagan");
  await expect(status).toContainText("Oflayn rejim");
  await expect(status).toContainText("Umumiy hamroh");

  await page.getByTestId("ui-language").selectOption("en");
  await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Memory" })).toBeVisible();

  // The choice survives a reload.
  await page.reload();
  await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();
  await page.getByTestId("ui-language").selectOption("uz");
});

test("unavailable modules are clearly marked", async ({ page }) => {
  await page.goto("/learn");
  const card = page.getByTestId("coming-soon");
  await expect(card).toContainText("Tez orada");
  await expect(card).toContainText("3-bosqichda");
  await expect(card).toContainText("IELTS");
});
