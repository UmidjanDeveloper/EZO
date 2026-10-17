import { expect, test } from "@playwright/test";

test("home shows only the EZO robot and conversation history", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("main").getByTestId("ezo-robot")).toBeVisible();
  await expect(page.getByText("Salom! Men EZO.")).toBeVisible();
  await expect(page.getByTestId("new-chat")).toBeVisible();
  // No agent or module menus.
  for (const hidden of ["Taqdimot agenti", "Studiya", "Tadqiqot", "Vazifalar"]) {
    await expect(page.getByText(hidden)).toHaveCount(0);
  }
});

test("chat: send a message, stream a reply, persist the conversation", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("offline-banner")).toBeVisible();

  await page.getByTestId("composer-input").fill("Salom, bugun nima qilamiz?");
  await page.keyboard.press("Enter");

  await expect(page.getByTestId("message-user")).toHaveText("Salom, bugun nima qilamiz?");
  await expect(page.getByTestId("message-assistant")).toContainText("oflayn rejimda");
  await expect(page).toHaveURL(/\/chat\/[0-9a-f-]{36}$/);
  await expect(page.getByTestId("chat-title")).toHaveText("Salom, bugun nima qilamiz?");
  await expect(page.getByTestId("conversation-list")).toContainText("Salom, bugun nima qilamiz?");

  // Reload: the conversation is loaded from the database.
  await page.reload();
  await expect(page.getByTestId("message-user")).toHaveText("Salom, bugun nima qilamiz?");
  await expect(page.getByTestId("message-assistant")).toContainText("oflayn rejimda");

  // Continue the same conversation.
  await page.getByTestId("composer-input").fill("Yana bir savol");
  await page.getByTestId("composer-send").click();
  await expect(page.getByTestId("message-user")).toHaveCount(2);
  await expect(page.getByTestId("message-assistant")).toHaveCount(2);

  // "New chat" starts fresh.
  await page.getByTestId("new-chat").click();
  await expect(page.getByTestId("message-user")).toHaveCount(0);
  await expect(page.getByText("Salom! Men EZO.")).toBeVisible();
});

test("routing happens behind the scenes and is visible in the debug trace", async ({ page }) => {
  await page.goto("/settings");
  await page.getByLabel("Debug izlarini ko‘rsatish").check();
  await page.getByTestId("new-chat").click();

  await page.getByTestId("composer-input").fill("Ezo, 15 slide presentation tayyorla");
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("message-assistant")).toContainText("oflayn");
  await expect(page.getByText("Taqdimot agenti")).toHaveCount(0); // no agent UI

  await page.getByTestId("show-trace").click();
  const trace = page.getByTestId("trace-panel");
  await expect(trace).toContainText("classify_intent");
  await expect(trace).toContainText("presentation");
});
