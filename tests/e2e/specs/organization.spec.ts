import { expect, test } from "@playwright/test";
import path from "node:path";

const FIXTURES = path.join(__dirname, "..", "fixtures");

// Offline mode (no AI keys): an official template needs no model, so this is
// deterministic. The approved Word template's letterhead must carry into the letter.
test("organization: formatting, logo, approved template and export, then a letter on the letterhead", async ({
  page,
}) => {
  page.on("dialog", (dialog) => void dialog.accept());
  await page.goto("/settings");
  const card = page.getByTestId("organization-profile");
  await expect(card.getByText("Logotip, shablon va namunalarni profil saqlangandan keyin qo'shasiz.")).toBeVisible();
  await card.getByTestId("org-name").fill("Xatirchi tumani hokimligi");
  await card.getByTestId("org-terms").fill("mutasaddi = mas'ul");
  await card.getByTestId("org-font-size").fill("13");
  await card.getByTestId("org-save").click();
  await expect(card.getByTestId("org-status")).toBeVisible();

  const files = card.getByTestId("organization-files");
  await files.getByTestId("org-logo-input").setInputFiles(path.join(FIXTURES, "logo.png"));
  await expect(files.getByTestId("org-logo")).toBeVisible();
  await files.getByRole("combobox").selectOption("xizmat_xati");
  await files.getByTestId("org-template-input").setInputFiles(path.join(FIXTURES, "blank.docx"));
  await expect(files.getByTestId("org-template")).toContainText("blank.docx");
  await files.getByTestId("org-example-input").setInputFiles({
    name: "namuna.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("Hurmatli rahbar! Ma'lum qilamizki, tadbir o'tkazildi."),
  });
  await expect(files.getByTestId("org-example")).toContainText("namuna.txt");

  // Saved values come back after a reload.
  await page.reload();
  await expect(card.getByTestId("org-terms")).toHaveValue("mutasaddi = mas'ul");
  await expect(card.getByTestId("org-font-size")).toHaveValue("13");
  await expect(files.getByTestId("org-template")).toHaveCount(1);

  const [exported] = await Promise.all([page.waitForEvent("download"), card.getByTestId("org-export").click()]);
  expect(exported.suggestedFilename()).toMatch(/\.zip$/);

  await page.goto("/");
  await page.getByTestId("composer-input").fill("Tashkilotimiz blankasida xizmat xati tayyorla");
  await page.keyboard.press("Enter");
  const artifact = page.getByTestId("message-assistant").getByTestId("artifact-card");
  await expect(artifact).toBeVisible({ timeout: 20_000 });
  await expect(artifact).toContainText("Xizmat xati");

  // Clean up for the other specs: the artifact, then the profile with its files.
  await page.goto("/artifacts");
  const rows = page.getByTestId("artifact-row");
  await expect(rows.first()).toBeVisible();
  for (let left = await rows.count(); left > 0; left -= 1) {
    await rows.first().locator("button[aria-expanded]").click(); // rows open collapsed
    await rows.first().getByTestId("artifact-delete").click();
    await expect(rows).toHaveCount(left - 1);
  }
  await page.goto("/settings");
  await card.getByTestId("org-delete").click();
  await expect(card.getByText("Hali tashkilot profili yo'q.")).toBeVisible();
});
