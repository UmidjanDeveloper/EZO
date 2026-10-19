import { expect, type Page, test } from "@playwright/test";

// Offline mode (no AI keys): a CV from the career profile and education templates need no
// model, so this is deterministic.
async function clearArtifacts(page: Page) {
  await page.goto("/artifacts");
  const rows = page.getByTestId("artifact-row");
  await expect(rows.first()).toBeVisible();
  for (let left = await rows.count(); left > 0; left -= 1) {
    await rows.first().locator("button[aria-expanded]").click(); // rows open collapsed
    await rows.first().getByTestId("artifact-delete").click();
    await expect(rows).toHaveCount(left - 1);
  }
}

test("career: save a profile, then get the CV built exactly from it", async ({ page }) => {
  page.on("dialog", (dialog) => void dialog.accept());
  await page.goto("/settings");
  const card = page.getByTestId("career-profile");
  await card.getByTestId("career-name").fill("Dilnoza Yusupova");
  await card.getByTestId("career-experience").fill("Tahlilchi | Vazirlik | 2021 | | Vaqtni 30% qisqartirdim");
  await card.getByTestId("career-skills").fill("Python, SQL");
  await card.getByTestId("career-save").click();
  await expect(card.getByRole("status")).toBeVisible();

  await page.goto("/");
  await page.getByTestId("composer-input").fill("Menga CV tayyorla");
  await page.keyboard.press("Enter");
  const artifact = page.getByTestId("message-assistant").getByTestId("artifact-card");
  await expect(artifact).toBeVisible({ timeout: 20_000 });
  await expect(artifact).toContainText("CV — Dilnoza Yusupova");

  await clearArtifacts(page);
  await page.goto("/settings");
  await page.getByTestId("career-profile").getByRole("button", { name: "O'chirish" }).click();
  await expect(page.getByTestId("career-profile").getByText("Hali karyera profili yo'q.", { exact: false })).toBeVisible();
});

test("education: a quiz template without a model gives Word and Excel", async ({ page }) => {
  page.on("dialog", (dialog) => void dialog.accept());
  await page.goto("/");
  await page.getByTestId("composer-input").fill("Fizika fanidan 5 ta test shablonini tuz");
  await page.keyboard.press("Enter");
  const cards = page.getByTestId("message-assistant").getByTestId("artifact-card");
  await expect(cards).toHaveCount(2, { timeout: 20_000 });
  await expect(cards.first()).toContainText("Test savollari");
  await clearArtifacts(page);
});
