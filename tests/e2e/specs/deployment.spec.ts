import { test, expect } from "@playwright/test";

test("the deployed browser discovers its public API without receiving server secrets", async ({ page }) => {
  const response = await page.request.get("/ezo-config");
  expect(response.status()).toBe(200);
  expect(response.headers()["cache-control"]).toBe("no-store");
  const source = await response.text();
  expect(source).toBe('window.__EZO_API_URL__ = "http://localhost:8100";');
  await page.goto("/");
  expect(await page.evaluate(() => (window as Window & { __EZO_API_URL__?: string }).__EZO_API_URL__))
    .toBe("http://localhost:8100");
  await expect(page.locator("body")).toBeVisible();
});
