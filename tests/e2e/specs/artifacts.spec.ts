import { expect, test } from "@playwright/test";

test("artifacts: save an answer, edit it into a new version, restore, download, rename, delete", async ({ page }) => {
  page.on("dialog", (dialog) => void dialog.accept());
  await page.goto("/");
  await page.getByTestId("composer-input").fill("Menga bugungi reja yozib ber");
  await page.keyboard.press("Enter");
  const answer = page.getByTestId("message-assistant");
  await expect(answer).toContainText("oflayn rejimda");

  // Save the answer: a card appears under it and stays after reload.
  await answer.getByTestId("save-answer").click();
  const card = answer.getByTestId("artifact-card");
  await expect(card).toBeVisible();
  await expect(card).toContainText("v1");
  await expect(answer.getByTestId("save-answer")).toBeDisabled();
  await page.reload();
  await expect(page.getByTestId("artifact-card")).toBeVisible();

  // Open it in “Yaratilganlar”.
  await page.getByTestId("artifact-card").getByRole("link").click();
  await expect(page).toHaveURL(/\/artifacts\?open=/);
  const row = page.getByTestId("artifact-row");
  await expect(row).toHaveCount(1);
  await expect(row.getByTestId("artifact-preview")).toContainText("oflayn rejimda");

  // Edit → version 2; version 1 is kept.
  await row.getByTestId("artifact-edit").click();
  await row.getByTestId("artifact-editor").fill("# Reja\n\n- Ertalab sport\n- Ish");
  await row.getByPlaceholder("Nima o‘zgardi? (ixtiyoriy)").fill("Qisqartirdim");
  await row.getByTestId("artifact-save-version").click();
  await expect(row.getByTestId("artifact-version")).toHaveCount(2);
  await expect(row.getByTestId("artifact-preview")).toContainText("Ertalab sport");
  await expect(row.getByTestId("artifact-version").first()).toContainText("Qisqartirdim");

  // Restore version 1 → version 3 (history kept).
  await row.getByTestId("artifact-restore").click();
  await expect(row.getByTestId("artifact-version")).toHaveCount(3);
  await expect(row.getByTestId("artifact-version").first()).toContainText("v1 dan tiklangan");
  await expect(row.getByTestId("artifact-preview")).toContainText("oflayn rejimda");

  // Download the current version.
  const [download] = await Promise.all([page.waitForEvent("download"), row.getByTestId("artifact-download").click()]);
  expect(download.suggestedFilename()).toMatch(/\.md$/);

  // Rename, then delete everything.
  await row.getByRole("button", { name: "Nomini o‘zgartirish" }).click();
  await row.getByTestId("artifact-rename-input").fill("Kunlik reja");
  await row.getByTestId("artifact-rename-input").press("Enter");
  await expect(row.getByTestId("artifact-title")).toHaveText("Kunlik reja");
  await row.getByTestId("artifact-delete").click();
  await expect(page.getByTestId("artifact-row")).toHaveCount(0);
  await expect(page.getByText("Hali hech narsa yaratilmagan.")).toBeVisible();
});
