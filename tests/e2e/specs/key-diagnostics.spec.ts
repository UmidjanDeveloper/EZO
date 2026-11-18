import { expect, test } from "@playwright/test";

// A configured AI key the provider rejected must be named on the chat screen, with what to do,
// instead of every feature failing silently. The status answer is shaped by the real API
// (offline in e2e), only the provider rows are replaced.
test("chat: a rejected AI key is shown plainly with how to fix it", async ({ page }) => {
  await page.route("**/api/status", async (route) => {
    const response = await route.fetch();
    const status = await response.json();
    status.offline_mode = false;
    status.providers = status.providers.map((p: Record<string, unknown>) =>
      p.name === "gemini"
        ? { ...p, configured: true, capabilities: ["chat"], key_warning: "unexpected_key_format", last_result: "auth" }
        : p,
    );
    await route.fulfill({ response, json: status });
  });
  await page.goto("/");
  const banner = page.getByTestId("key-problem-banner");
  await expect(banner).toContainText("AI kaliti rad etildi — Google Gemini");
  await expect(banner).toContainText("AIza");
  await expect(banner).toContainText("--force-recreate api");
  await expect(page.getByTestId("offline-banner")).toHaveCount(0);
});

test("chat: a key that only looks wrong is flagged before it is used", async ({ page }) => {
  await page.route("**/api/status", async (route) => {
    const response = await route.fetch();
    const status = await response.json();
    status.offline_mode = false;
    status.providers = status.providers.map((p: Record<string, unknown>) =>
      p.name === "openai" ? { ...p, configured: true, capabilities: ["chat"], key_warning: "unexpected_key_format", last_result: null } : p,
    );
    await route.fulfill({ response, json: status });
  });
  await page.goto("/");
  await expect(page.getByTestId("key-problem-banner")).toContainText("AI kaliti noto‘g‘ri ko‘rinishda — OpenAI");
});
