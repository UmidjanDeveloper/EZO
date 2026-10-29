import { expect, test } from "@playwright/test";

const API_PORT = Number(process.env.E2E_API_PORT ?? 8100);

test("IELTS text feedback never invents a band or pronunciation score", async ({ page }) => {
  await page.goto("/ielts");
  const created = page.waitForResponse(response =>
    response.request().method() === "POST" && response.url().endsWith("/api/ielts/sessions"));
  await page.getByRole("button", { name: "Yangi imtihon boshlash", exact: true }).first().click();
  const creation = await created;
  expect(creation.status()).toBe(200);
  const { id } = await creation.json();
  try {
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
  } finally {
    // Only this test's session: later journeys share the fixture owner's database.
    const deleted = await page.request.delete(`http://localhost:${API_PORT}/api/language/sessions/${id}?confirm=true`);
    expect(deleted.status()).toBe(204);
  }
});
