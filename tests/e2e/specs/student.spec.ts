import { expect, test } from "@playwright/test";

test("student: real text ingestion, durable worker, Unicode reader and offline honesty", async ({ page }) => {
  await page.goto("/student");
  await expect(page.getByRole("heading", { name: "EZO Student" })).toBeVisible();
  await expect(page.getByText("AI provayder ulanmagan.", { exact: false })).toBeVisible();
  await page.getByLabel("Yoki o‘rganish uchun matn").fill("Fotosintez quyosh energiyasini saqlaydi. Ўзбекистон 🙂");
  await page.getByRole("button", { name: "Matnni saqlash" }).click();
  await page.getByRole("button", { name: /O_quv matni/ }).first().click();
  await expect(page.getByRole("article", { name: "Manba matni" })).toContainText("Ўзбекистон 🙂");
  await expect(page.getByRole("button", { name: "Javob olish", exact: true })).toBeDisabled();
  await page.locator("input[type=file]").setInputFiles({ name: "queue.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-queued-repository-fixture") });
  await page.getByRole("button", { name: /queue.pdf/ }).click();
  await page.getByRole("button", { name: "Bekor qilish", exact: true }).click();
  await expect(page.getByRole("button", { name: /queue.pdf/ })).toContainText("Bekor qilindi");
});

test("student: mocked AI UI renders citations and interactive quiz", async ({ page }) => {
  // UI contract test only. Real container/backend/mock-model end-to-end lives in
  // tests/integration/test_student_executor.py; no live provider is claimed here.
  await page.route("**/api/student/status", route => route.fulfill({ json: { ai_provider_configured: true } }));
  await page.route("**/api/student/documents/*/learn", route => route.fulfill({ json: {
    status: "generated", text: "Fotosintez [1].", generated: true, provider: "fixture-mock",
    citations: [{ n: 1, excerpt: "Fotosintez quyosh energiyasini saqlaydi.", location: "p. 1" }],
    quiz: { items: [{ question: "Nima saqlanadi?", choices: ["Energiya", "Qum"], answer: 0, explanation: "Energiya [1]." }] },
  } }));
  await page.goto("/student");
  await page.getByLabel("Yoki o‘rganish uchun matn").fill("Quiz uchun alohida hujjat. Fotosintez quyosh energiyasini saqlaydi.");
  await page.getByRole("button", { name: "Matnni saqlash" }).click();
  await page.getByRole("button", { name: /O_quv matni/ }).first().click();
  await expect(page.getByRole("article", { name: "Manba matni" })).toBeVisible();
  await page.getByRole("button", { name: "Test tuzish" }).click();
  await expect(page.getByText("AI izohi (fixture-mock)", { exact: false })).toBeVisible();
  await page.getByLabel("Energiya", { exact: true }).check();
  await expect(page.getByText("To‘g‘ri.", { exact: false })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Manbalar" })).toBeVisible();
});

test("student: bounded library pagination keeps older books accessible", async ({ page }) => {
  const books = Array.from({ length: 31 }, (_, i) => ({ title: `Kitob ${i + 1}`, job: {
    id: `fixture-${i}`, document_id: `document-${i}`, project_id: null,
    state: "queued", attempts: 0, max_attempts: 3, error_message: null,
    parser_version: "isolated-extraction/v1",
  } }));
  await page.route("**/api/student/library?*", route => {
    const offset = Number(new URL(route.request().url()).searchParams.get("offset") ?? 0);
    return route.fulfill({ json: books.slice(offset, offset + 31) });
  });
  await page.goto("/student");
  await expect(page.getByRole("button", { name: /Kitob 1 Navbatda/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /Kitob 31/ })).toHaveCount(0);
  await page.getByRole("button", { name: "Keyingi hujjatlar", exact: true }).click();
  await expect(page.getByRole("button", { name: /Kitob 31/ })).toBeVisible();
  await expect(page.getByRole("button", { name: "Keyingi hujjatlar", exact: true })).toBeDisabled();
  await page.getByRole("button", { name: "Oldingi hujjatlar", exact: true }).click();
  await expect(page.getByRole("button", { name: /Kitob 1 Navbatda/ })).toBeVisible();
});
