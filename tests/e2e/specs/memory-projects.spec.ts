import { expect, test } from "@playwright/test";

test("memory: EZO remembers explicit facts and the user can delete them", async ({ page }) => {
  // Consent-first: opt in to explicit memory consent in the Memory hub first
  await page.goto("/memory");
  const consentToggle = page.getByTestId("memory-consent-toggle");
  await expect(consentToggle).toBeVisible();
  await consentToggle.click();
  await expect(page.getByTestId("memory-consent-badge")).toBeVisible();

  await page.goto("/");
  await page.getByTestId("composer-input").fill("Eslab qol: men yashil choyni yaxshi ko‘raman.");
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("message-assistant")).toContainText("oflayn");
  await expect(page.getByText("Eslab qoldim")).toBeVisible();

  await page.goto("/memory");
  const list = page.getByTestId("memory-list");
  await expect(list).toContainText("men yashil choyni yaxshi ko‘raman.");

  // Add one manually, then delete both.
  await page.getByLabel("Qo‘shish").fill("Men qisqa javoblarni afzal ko‘raman");
  await page.getByTestId("memory-form").getByRole("button", { name: "Qo‘shish" }).click();
  await expect(list.locator("li")).toHaveCount(2);

  page.on("dialog", (dialog) => void dialog.accept());
  await page.getByRole("button", { name: "Hammasini o‘chirish" }).click();
  await expect(page.getByText("Hozircha xotira bo‘sh.")).toBeVisible();
});

test("projects: create a project and chat inside it", async ({ page }) => {
  await page.goto("/projects");
  await page.getByLabel("Nomi").fill("EZO veb-sayti");
  await page.getByLabel("Tavsif").fill("Landing page loyihasi");
  await page.getByRole("button", { name: "Loyiha yaratish" }).click();

  const card = page.getByTestId("project-list").getByRole("link", { name: /EZO veb-sayti/ });
  await expect(card).toBeVisible();
  await card.click();
  await expect(page.getByRole("heading", { name: "EZO veb-sayti" })).toBeVisible();

  await page.getByTestId("project-new-chat").click();
  await expect(page.getByText("EZO veb-sayti").first()).toBeVisible(); // project badge
  await page.getByTestId("composer-input").fill("Biz to‘q ko‘k rangni tanlashga qaror qildik.");
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("message-assistant")).toContainText("oflayn");

  await page.goto("/projects");
  await page.getByTestId("project-list").getByRole("link", { name: /EZO veb-sayti/ }).click();
  await expect(page.getByText("Biz to‘q ko‘k rangni tanlashga qaror qildik.").first()).toBeVisible();
});
