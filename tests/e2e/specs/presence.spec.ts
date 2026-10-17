import { expect, test } from "@playwright/test";

test("EZO presence: idle orb on the home screen", async ({ page }) => {
  await page.goto("/");
  const presence = page.locator("main").getByTestId("ezo-presence");
  await expect(presence).toHaveAttribute("data-state", "idle");
  await expect(presence).toHaveAttribute("aria-busy", "false");
  await expect(page.getByTestId("ezo-status")).toHaveCount(0); // nothing to report while idle
});

test("EZO presence: header status shows the reply finishing, then settles to idle", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("composer-input").fill("Salom!");
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("message-assistant")).toContainText("oflayn rejimda");

  const status = page.getByTestId("ezo-status");
  await expect(status).toHaveAttribute("data-state", "completed");
  await expect(status).toHaveText("Tayyor");
  await expect(status).toHaveCount(0, { timeout: 5_000 }); // back to idle
});

test("EZO presence: voice stage starts idle and keeps the robot face", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("mode-voice").click();
  const presence = page.getByTestId("voice-stage").getByTestId("ezo-presence");
  await expect(presence).toHaveAttribute("data-state", "idle");
  await expect(presence.getByTestId("ezo-robot")).toBeVisible();
});
