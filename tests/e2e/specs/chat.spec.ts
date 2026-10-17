import { expect, test } from "@playwright/test";

test("chat: send a message, stream a reply, persist the conversation", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("Sen bilan o‘sadigan shaxsiy sun’iy intellekt").first()).toBeVisible();
  await expect(page.getByTestId("offline-banner")).toBeVisible();

  await page.getByTestId("composer-input").fill("Salom, bugun nima qilamiz?");
  await page.keyboard.press("Enter");

  await expect(page.getByTestId("message-user")).toHaveText("Salom, bugun nima qilamiz?");
  const reply = page.getByTestId("message-assistant");
  await expect(reply).toContainText("oflayn rejimda");
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
  await expect(page.getByTestId("chat-title")).toHaveText("Yangi suhbat");
});

test("routing: specialised requests are routed and limitations are shown", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("composer-input").fill("Ezo, 15 slide presentation tayyorla");
  await page.keyboard.press("Enter");

  await expect(page.getByTestId("agent-fallback")).toContainText("Taqdimot agenti");
  await expect(page.getByTestId("agent-fallback")).toContainText("4-bosqich");

  // The debug trace shows the routing decision.
  await page.getByTestId("toggle-debug").click();
  await page.getByTestId("show-trace").click();
  const trace = page.getByTestId("trace-panel");
  await expect(trace).toContainText("classify_intent");
  await expect(trace).toContainText("presentation");
  await expect(trace).toContainText("select_agent");
});
