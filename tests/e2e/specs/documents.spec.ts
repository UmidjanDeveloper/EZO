import { expect, test } from "@playwright/test";

// Offline mode (no AI keys): conversion is deterministic and needs no model, so it really works.
test("documents: attach a file, convert it to PDF, download the PDF and its Word export", async ({ page }) => {
  page.on("dialog", (dialog) => void dialog.accept());
  await page.goto("/");
  await page.getByTestId("composer-file-input").setInputFiles({
    name: "shartnoma.md",
    mimeType: "text/markdown",
    buffer: Buffer.from("# Shartnoma\n\n## Shartlar\n\nIjara narxi oyiga 4 500 000 so'm.\n\n- To'lov: har oyning 5-sanasi"),
  });
  await expect(page.getByTestId("attachment").getByTestId("knowledge-status")).toHaveAttribute(
    "data-status",
    "partial",
    { timeout: 15_000 },
  );

  await page.getByTestId("composer-input").fill("Shu faylni PDF ga aylantir");
  await page.keyboard.press("Enter");
  const answer = page.getByTestId("message-assistant");
  const card = answer.getByTestId("artifact-card");
  await expect(card).toBeVisible();
  await expect(card).toContainText("Shartnoma");

  // The main file is the PDF.
  const [pdf] = await Promise.all([page.waitForEvent("download"), card.getByRole("button", { name: "Yuklab olish" }).click()]);
  expect(pdf.suggestedFilename()).toBe("Shartnoma.pdf");

  // The other formats are listed in “Yaratilganlar”.
  await card.getByRole("link").click();
  const row = page.getByTestId("artifact-row");
  const exports = row.getByTestId("artifact-exports");
  await expect(exports.getByTestId("export-docx")).toHaveText(/Word/);
  await expect(exports.getByTestId("export-markdown")).toBeVisible();
  const [docx] = await Promise.all([page.waitForEvent("download"), exports.getByTestId("export-docx").click()]);
  expect(docx.suggestedFilename()).toBe("Shartnoma.docx");

  // Clean up: the other specs expect an empty knowledge base and no artifacts.
  await row.getByTestId("artifact-delete").click();
  await expect(page.getByTestId("artifact-row")).toHaveCount(0);
  await page.goto("/knowledge");
  await page.getByTestId("knowledge-document").getByTestId("knowledge-delete").click();
  await expect(page.getByTestId("knowledge-document")).toHaveCount(0);
});
