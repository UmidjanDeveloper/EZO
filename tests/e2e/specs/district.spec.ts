import { expect, test } from "@playwright/test";

const today = new Date();
const iso = (d: Date) => d.toISOString().slice(0, 10);
const start = new Date(today.getTime() - 10 * 86_400_000);
const deadline = new Date(today.getTime() + 10 * 86_400_000);

const TABLE = [
  "F.I.Sh;Telefon;Mahalla;Reja;Bajarildi",
  "Aliyev Botir;;Navbahor;100;5",
  "Karimova Dilnoza;;Guliston;100;70",
].join("\n");

test("district center: add a project, import a table, see who is behind, draft a warning", async ({ page }) => {
  page.on("dialog", (dialog) => void dialog.accept());
  await page.goto("/district");
  await expect(page.getByRole("heading", { name: "Tuman markazi" })).toBeVisible();
  const channels = page.getByTestId("district-channels");
  await expect(channels).toContainText("SMS ulanmagan");

  await page.getByTestId("district-new").click();
  await page.getByTestId("district-name").fill("Xatlov E2E");
  await page.getByLabel("O‘lchov birligi").fill("xonadon");
  await page.getByLabel("Boshlanish").fill(iso(start));
  await page.getByLabel("Muddat").fill(iso(deadline));
  await page.getByTestId("district-create").click();

  const detail = page.getByTestId("district-detail");
  await expect(detail).toContainText("Xatlov E2E");
  await detail.getByTestId("district-import").setInputFiles({
    name: "xatlov.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(TABLE, "utf-8"),
  });
  await expect(detail.getByTestId("district-message")).toContainText("2 qator o‘qildi");
  await expect(detail.getByTestId("district-summary")).toContainText("75 / 200 xonadon (37.5%)");

  const aliyev = detail.getByTestId("district-person").filter({ hasText: "Aliyev Botir" });
  await expect(aliyev).toContainText("Orqada");
  await expect(detail.getByTestId("district-person").filter({ hasText: "Karimova" })).not.toContainText("Orqada");
  await expect(page.getByTestId("district-project").filter({ hasText: "Xatlov E2E" })).toContainText("Orqada: 1");

  // A warning is a draft with its exact text; with no phone or Telegram it cannot be sent.
  await aliyev.getByTestId("district-warn").click();
  const card = detail.getByTestId("district-notice");
  await expect(card.getByTestId("notice-status")).toHaveText("Qoralama — hali yuborilmagan");
  await expect(card.getByTestId("notice-text")).toHaveValue(/rejangiz 100 xonadon, bajarilgani 5 \(5%\)/);
  await expect(card).toContainText("Aloqa yo‘q");
  await expect(card.getByTestId("notice-send")).toBeDisabled();
});
