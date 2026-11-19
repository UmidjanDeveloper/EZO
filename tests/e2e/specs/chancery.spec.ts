import { expect, test } from "@playwright/test";

test("devonxona: register an appeal, answer it, add a task and finish it", async ({ page }) => {
  await page.goto("/chancery");
  await expect(page.getByRole("heading", { name: "Devonxona" })).toBeVisible();

  await page.getByTestId("appeal-new").click();
  await page.getByTestId("appeal-applicant").fill("Karimov Aziz");
  await page.getByTestId("appeal-summary").fill("Ko‘chadagi chiroqlar yonmayapti.");
  await page.getByTestId("appeal-add").click();
  const appeal = page.getByTestId("appeal-row").filter({ hasText: "Karimov Aziz" });
  await expect(appeal).toContainText(/M-\d{4}-0001/);
  await expect(appeal.getByTestId("chancery-state")).toHaveText("Yangi");
  await appeal.getByTestId("appeal-answered").click();
  await expect(appeal.getByTestId("chancery-state")).toHaveText("Javob berilgan");

  await page.getByTestId("chancery-tab-tasks").click();
  await page.getByTestId("task-title").fill("Chiroqlarni tiklash");
  await page.getByTestId("task-add").click();
  const task = page.getByTestId("task-row").filter({ hasText: "Chiroqlarni tiklash" });
  await expect(task).toContainText(/T-\d{4}-0001/);
  await task.getByTestId("task-done").click();
  await expect(task.getByTestId("chancery-state")).toHaveText("Bajarilgan");
});
