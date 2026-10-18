import { expect, test } from "@playwright/test";

// Offline mode (no AI keys): templates need no model, so this is deterministic.
test("writing: save an organization profile, then get an official template in chat", async ({ page }) => {
  page.on("dialog", (dialog) => void dialog.accept());
  await page.goto("/settings");
  const card = page.getByTestId("organization-profile");
  await card.getByTestId("org-name").fill("Xatirchi tumani hokimligi");
  await card.getByTestId("org-save").click();
  await expect(card.getByRole("status")).toBeVisible();

  await page.goto("/");
  await page.getByTestId("composer-input").fill("Xizmat xati shablonini tayyorla");
  await page.keyboard.press("Enter");
  const artifact = page.getByTestId("message-assistant").getByTestId("artifact-card");
  await expect(artifact).toBeVisible({ timeout: 20_000 });
  await expect(artifact).toContainText("Xizmat xati");
  const [download] = await Promise.all([
    page.waitForEvent("download"),
    artifact.getByRole("button", { name: "Yuklab olish" }).click(),
  ]);
  expect(download.suggestedFilename()).toBe("Xizmat xati.docx");

  // Clean up for the other specs.
  await artifact.getByRole("link").click();
  const rows = page.getByTestId("artifact-row");
  await expect(rows.first()).toBeVisible();
  for (let left = await rows.count(); left > 0; left -= 1) {
    await rows.first().getByTestId("artifact-delete").click();
    await expect(rows).toHaveCount(left - 1);
  }
  await page.goto("/settings");
  await page.getByTestId("organization-profile").getByRole("button", { name: "O'chirish" }).click();
  await expect(page.getByTestId("organization-profile").getByText("Hali tashkilot profili yo'q.")).toBeVisible();
});
