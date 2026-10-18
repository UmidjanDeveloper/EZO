import { expect, test } from "@playwright/test";

// Offline mode (no AI keys): Latin ↔ Cyrillic and the glossary need no model; translation
// itself says plainly that it needs an AI provider.
test("translation: script conversion, glossary, honest offline translation", async ({ page }) => {
  await page.goto("/translate");
  const card = page.getByTestId("translate-card");
  await card.getByTestId("translate-input").fill("O'zbekiston Respublikasi, Toshkent shahri");
  await card.getByTestId("translit-cyrillic").click();
  await expect(card.getByTestId("translate-output")).toHaveValue("Ўзбекистон Республикаси, Тошкент шаҳри");
  await card.getByTestId("translate-input").fill("Ғафур Ғулом кўчаси");
  await card.getByTestId("translit-latin").click();
  await expect(card.getByTestId("translate-output")).toHaveValue("G'afur G'ulom ko'chasi");

  await card.getByTestId("translate-run").click();
  await expect(card.getByTestId("translate-error")).toBeVisible();

  const glossary = page.getByTestId("glossary");
  await glossary.getByTestId("glossary-source").fill("hokimlik");
  await glossary.getByTestId("glossary-target").fill("khokimiyat");
  await glossary.getByTestId("glossary-add").click();
  const list = glossary.getByTestId("glossary-list");
  await expect(list).toContainText("hokimlik → khokimiyat");

  // Clean up for the other specs.
  await list.getByRole("button", { name: "O'chirish" }).click();
  await expect(glossary.getByText("Glossariy bo'sh.")).toBeVisible();
});
