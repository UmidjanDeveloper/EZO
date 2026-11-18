import { expect, test } from "@playwright/test";

// Settings → "Kalitlarni tekshirish": the owner asks the API to make one tiny real request per
// configured provider, then sees each outcome. The e2e API has no provider, so the configured
// provider rows and the probe answer are supplied here; the page wiring is real.
test("settings: the owner tests the AI keys and sees which one was rejected", async ({ page }) => {
  let probed = false;
  await page.route("**/api/status/providers/test", async (route) => {
    expect(route.request().method()).toBe("POST");
    probed = true;
    await route.fulfill({ json: { offline: false, providers: [{ name: "gemini", display_name: "Google Gemini", result: "auth", key_warning: "unexpected_key_format" }] } });
  });
  await page.route("**/api/status", async (route) => {
    const response = await route.fetch();
    const status = await response.json();
    status.offline_mode = false;
    status.providers = status.providers.map((p: Record<string, unknown>) =>
      p.name === "gemini"
        ? { ...p, configured: true, capabilities: ["chat"], key_warning: "unexpected_key_format", last_result: probed ? "auth" : null }
        : p,
    );
    await route.fulfill({ response, json: status });
  });
  await page.goto("/settings");
  const gemini = page.getByTestId("provider-gemini");
  await expect(gemini).toContainText("Kalit noto‘g‘ri ko‘rinishda");
  await page.getByTestId("test-provider-keys").click();
  await expect(gemini).toContainText("Kalit rad etildi");
  expect(probed).toBe(true);
});
