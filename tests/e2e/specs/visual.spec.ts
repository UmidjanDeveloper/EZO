import { expect, test } from "@playwright/test";

// A 2×2 PNG, used as the preview of a generated image.
const PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAFklEQVR4nGP8z8DAwMDAxMDAwMDAAAANHQEDasKb6QAAAABJRU5ErkJggg==",
  "base64",
);
const IMAGE_ID = "00000000-0000-4000-8000-0000000000aa";

test("visual: without an AI provider no image is pretended", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("composer-input").fill("Kosmosdagi mushuk rasmini chiz");
  await page.keyboard.press("Enter");
  const answer = page.getByTestId("message-assistant");
  await expect(answer).toContainText("oflayn rejimda");
  await expect(answer.getByTestId("artifact-card")).toHaveCount(0);
});

test("visual: a generated image is shown right in the conversation", async ({ page }) => {
  // The e2e API runs offline, so the reply is real but gets one image artifact added.
  await page.route("**/api/chat/stream", async (route) => {
    const response = await route.fetch();
    const events = (await response.text()).split("\n\n").map((block) => {
      if (!block.startsWith("event: done")) return block;
      const [head, data] = block.split("\ndata: ");
      const payload = JSON.parse(data!);
      payload.message.metadata = {
        ...payload.message.metadata,
        artifacts: [{ id: IMAGE_ID, title: "Kosmosdagi mushuk", type: "image", version: 1 }],
      };
      return `${head}\ndata: ${JSON.stringify(payload)}`;
    });
    await route.fulfill({ response, body: events.join("\n\n") });
  });
  await page.route(`**/api/artifacts/${IMAGE_ID}/versions/1/exports/preview-1`, (route) =>
    route.fulfill({ body: PNG, contentType: "image/png", headers: { "Content-Disposition": "inline" } }),
  );

  await page.goto("/");
  await page.getByTestId("composer-input").fill("Kosmosdagi mushuk rasmini chiz");
  await page.keyboard.press("Enter");
  const card = page.getByTestId("message-assistant").getByTestId("artifact-card");
  await expect(card).toContainText("Kosmosdagi mushuk");
  await expect(card).toContainText("Rasm");
  const image = card.getByTestId("artifact-image");
  await expect(image).toBeVisible();
  await expect(image).toHaveAttribute("alt", "Kosmosdagi mushuk");
  expect(await image.evaluate((img: HTMLImageElement) => img.naturalWidth)).toBe(2);
});
