import { expect, test } from "@playwright/test";

// Offline e2e (no AI key): practice needs a model, so EZO says so honestly; the progress page
// works and shows the simulator disclaimer.
test("language: the practice page is reachable and honest", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: "Til mashg'ulotlari" }).click();
  await expect(page).toHaveURL(/\/language$/);
  await expect(page.getByRole("heading", { name: "Til mashg'ulotlari" })).toBeVisible();
  await expect(page.getByTestId("language-disclaimer")).toContainText("rasmiy IELTS balli emas");
  await expect(page.getByText("Hali mashg'ulot yo'q.")).toBeVisible();
  await expect(page.getByTestId("language-goal")).toContainText("Maqsad belgilanmagan");

  // Asking to practise without an AI provider: the coach is chosen, nothing is faked or stored.
  await page.goto("/");
  await page.getByTestId("composer-input").fill("IELTS speaking qilamiz");
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("message-assistant")).toContainText("oflayn rejimda");
  await page.goto("/language");
  await expect(page.getByText("Hali mashg'ulot yo'q.")).toBeVisible();
});
