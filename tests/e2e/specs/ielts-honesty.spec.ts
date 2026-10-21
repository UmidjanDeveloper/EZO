import { expect, test } from "@playwright/test";

test("IELTS text feedback never invents a band or pronunciation score", async ({ page }) => {
  await page.goto("/ielts");
  await page.getByRole("button", { name: "Yangi imtihon boshlash", exact: true }).first().click();
  await page.locator("textarea").fill("I enjoy learning because it helps me understand new ideas.");
  const evaluated = page.waitForResponse(response => response.url().endsWith("/api/ielts/evaluate"));
  await page.getByRole("button", { name: "Javobni yuborish", exact: true }).click();
  const response = await evaluated;
  expect(response.status()).toBe(200);
  const result = await response.json();
  expect(result.pronunciation_score).toBeNull();
  expect(result.estimated_band).toBeNull();
  await expect(page.getByText(/No AI assessment was performed/)).toBeVisible();
  await expect(page.getByText("Band —", { exact: true })).toBeVisible();
});
