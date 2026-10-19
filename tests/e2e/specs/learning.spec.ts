import { expect, test } from "@playwright/test";

// Knowledge OS: EZO learns a local fixture documentation site (served by Playwright on
// 127.0.0.1:8200) without an AI key: reading and keyword indexing need no model.
test("knowledge OS: learn a documentation site, see its status, pages and flags, then delete it", async ({
  page,
}) => {
  page.on("dialog", (dialog) => void dialog.accept());
  await page.goto("/knowledge");
  const section = page.getByTestId("learned-sources");
  await expect(section.getByTestId("learned-empty")).toBeVisible();

  // An unknown target is refused with a clear message.
  await section.getByTestId("learn-target").fill("just some words");
  await section.getByTestId("learn-submit").click();
  await expect(section.getByRole("alert")).toBeVisible();

  await section.getByTestId("learn-target").fill("http://127.0.0.1:8200/guide/");
  await section.getByTestId("learn-library").fill("E2E hujjatlar");
  await section.getByTestId("learn-submit").click();
  const source = section.getByTestId("learned-source");
  await expect(source).toHaveAttribute("data-status", "indexed", { timeout: 30_000 });
  await expect(source.getByTestId("learned-status")).toHaveText("O'rganildi");
  await expect(section.getByTestId("learned-library")).toContainText("E2E hujjatlar");
  await expect(source.getByTestId("learned-flags")).toBeVisible(); // the injection attempt
  await expect(source.getByTestId("learned-license-review")).toBeVisible(); // no licence found

  await source.locator("button[aria-expanded]").click();
  const documents = source.getByTestId("learned-documents");
  await expect(documents).toContainText("Quickstart");
  await expect(documents).toContainText("Widget guide");
  await expect(documents).not.toContainText("Private"); // robots.txt
  await expect(documents).not.toContainText("Outside"); // outside the folder
  // Learned pages stay under their source, not in the list of the user's own files.
  await expect(page.getByTestId("knowledge-list")).not.toContainText("Quickstart");
  await expect(page.getByTestId("knowledge-list")).not.toContainText("Widget guide");

  await source.getByTestId("learned-delete").click();
  await expect(section.getByTestId("learned-source")).toHaveCount(0);
  await section.getByRole("button", { name: "Kutubxonani o'chirish" }).click();
  await expect(section.getByTestId("learned-empty")).toBeVisible();
});
