import { expect, test } from "@playwright/test";
import path from "node:path";

const FIXTURES = path.join(__dirname, "..", "fixtures");

// Offline mode (no AI keys): PDF operations are deterministic and need no model.
test("pdf: attach two PDFs, merge them in chat, see the preview and download the result", async ({ page }) => {
  page.on("dialog", (dialog) => void dialog.accept());
  await page.goto("/");
  await page.getByTestId("composer-file-input").setInputFiles([path.join(FIXTURES, "a.pdf"), path.join(FIXTURES, "b.pdf")]);
  const chips = page.getByTestId("attachment");
  await expect(chips).toHaveCount(2);
  for (const chip of await chips.all()) {
    await expect(chip.getByTestId("knowledge-status")).toBeVisible({ timeout: 15_000 });
  }

  await page.getByTestId("composer-input").fill("Shu PDFlarni birlashtir");
  await page.keyboard.press("Enter");

  // The user's message shows which files it is about, in order; the composer is cleared.
  const sent = page.getByTestId("message-attachments");
  await expect(sent).toContainText("a.pdf");
  await expect(sent).toContainText("b.pdf");
  await expect(page.getByTestId("attachment")).toHaveCount(0);

  const card = page.getByTestId("message-assistant").getByTestId("artifact-card");
  await expect(card).toBeVisible({ timeout: 20_000 });
  await expect(card.getByTestId("artifact-image")).toBeVisible(); // first-page preview
  const [download] = await Promise.all([page.waitForEvent("download"), card.getByRole("button", { name: "Yuklab olish" }).click()]);
  expect(download.suggestedFilename()).toMatch(/\.pdf$/);

  // Clean up for the other specs: delete what this test created, whatever the count.
  await card.getByRole("link").click();
  const rows = page.getByTestId("artifact-row");
  await expect(rows.first()).toBeVisible();
  for (let left = await rows.count(); left > 0; left -= 1) {
    await rows.first().getByTestId("artifact-delete").click();
    await expect(rows).toHaveCount(left - 1);
  }
  await page.goto("/knowledge");
  const documents = page.getByTestId("knowledge-document");
  await expect(documents.first()).toBeVisible();
  for (let left = await documents.count(); left > 0; left -= 1) {
    await documents.first().getByTestId("knowledge-delete").click();
    await expect(documents).toHaveCount(left - 1);
  }
});
