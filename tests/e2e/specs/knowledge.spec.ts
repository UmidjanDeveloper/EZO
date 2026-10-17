import { expect, test } from "@playwright/test";

const NOTE = Buffer.from("EZO loyihasining ichki kod nomi Samarqand-7. Uni Aziz boshqaradi.");

test("knowledge: upload a file, see it read, open details, delete it", async ({ page }) => {
  page.on("dialog", (dialog) => void dialog.accept());
  await page.goto("/knowledge");
  // Offline e2e has no embedding key: EZO says honestly that only keyword search works.
  await expect(page.getByTestId("semantic-off")).toBeVisible();

  await page.getByTestId("knowledge-file-input").setInputFiles({ name: "loyiha.txt", mimeType: "text/plain", buffer: NOTE });
  const row = page.getByTestId("knowledge-document");
  await expect(row).toHaveCount(1);
  await expect(row.getByTestId("knowledge-title")).toHaveText("loyiha");
  await expect(row.getByTestId("knowledge-status")).toHaveAttribute("data-status", "partial", { timeout: 15_000 });

  await row.getByRole("button", { name: "Matndan namunalar" }).click();
  await expect(row).toContainText("Samarqand-7");
  await expect(row).toContainText("joriy");

  // Same content again is recognised as a duplicate.
  await page.getByTestId("knowledge-file-input").setInputFiles({ name: "copy.txt", mimeType: "text/plain", buffer: NOTE });
  await expect(page.getByTestId("knowledge-notice")).toHaveText("Bu fayl allaqachon yuklangan.");
  await expect(row).toHaveCount(1);

  await row.getByTestId("knowledge-delete").click();
  await expect(page.getByTestId("knowledge-document")).toHaveCount(0);
});

test("knowledge: unsupported files are rejected with a clear message", async ({ page }) => {
  await page.goto("/knowledge");
  await page.getByTestId("knowledge-file-input").setInputFiles({ name: "setup.exe", mimeType: "application/octet-stream", buffer: Buffer.from("MZ") });
  await expect(page.getByTestId("knowledge-notice")).toContainText("not supported");
  await expect(page.getByTestId("knowledge-document")).toHaveCount(0);
});

test("chat: attach a file from the composer and see its status", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("composer-file-input").setInputFiles({
    name: "eslatma.md",
    mimeType: "text/markdown",
    buffer: Buffer.from("# Eslatma\n\nUchrashuv juma kuni soat 15:00 da."),
  });
  const chip = page.getByTestId("attachment");
  await expect(chip).toContainText("eslatma.md");
  await expect(chip.getByTestId("knowledge-status")).toHaveAttribute("data-status", "partial", { timeout: 15_000 });

  await page.goto("/knowledge");
  await expect(page.getByTestId("knowledge-title")).toHaveText("Eslatma");
});
