import { expect, test } from "@playwright/test";

// UI contract for the two Student surfaces the backend had without a page: owner-defined
// learning paths (server-evaluated, self-reported recall only) and a cited comparison of
// documents. Routes are mocked with the real response shapes; the server-side rules live in
// apps/api tests.

const library = [
  { title: "Hisobot 2025", job: { id: "j1", document_id: "d1", project_id: null, state: "completed", attempts: 1, max_attempts: 3, error_message: null, parser_version: "isolated-extraction/v1" } },
  { title: "Hisobot 2026", job: { id: "j2", document_id: "d2", project_id: null, state: "completed", attempts: 1, max_attempts: 3, error_message: null, parser_version: "isolated-extraction/v1" } },
];
const cards = [
  { id: "c1", document_id: "d1", revision_id: "r1", chunk_id: "k1", project_id: null, front: "Daromad 2025", back: "12%", quote: "12%", due_at: "2026-10-27T00:00:00Z", version: 1, interval_days: 1 },
  { id: "c2", document_id: "d2", revision_id: "r2", chunk_id: "k2", project_id: null, front: "Daromad 2026", back: "15%", quote: "15%", due_at: "2026-10-27T00:00:00Z", version: 1, interval_days: 1 },
];

test("student: a learning path is built from saved cards and evaluated by the server without mastery claims", async ({ page }) => {
  const paths: Record<string, unknown>[] = [];
  let created: Record<string, unknown> | null = null;
  await page.route("**/api/student/status", (route) => route.fulfill({ json: { ai_provider_configured: true } }));
  await page.route("**/api/student/library?*", (route) => route.fulfill({ json: library }));
  await page.route("**/api/student/cards", (route) => route.fulfill({ json: cards }));
  await page.route("**/api/student/progress", (route) => route.fulfill({ json: { active_cards: 2, due_cards: 0, review_events: 0, reviewed_cards: 0, assessment: "self_reported_recall" } }));
  await page.route("**/api/student/practice-plan", (route) => route.fulfill({ json: { items: [], empty_reason: "nothing_due" } }));
  await page.route("**/api/student/learning-paths", (route) => {
    if (route.request().method() === "POST") {
      created = route.request().postDataJSON() as Record<string, unknown>;
      paths.push({ id: "p1", title: created.title, language: created.language, project_id: null, goal_id: null, state: "active", version: 0, created_at: "2026-10-26T00:00:00Z", assessment: "self_reported_recall", policy: "source-recall-path/v1" });
      return route.fulfill({ status: 201, json: paths[0] });
    }
    return route.fulfill({ json: paths });
  });
  await page.route("**/api/student/learning-paths/p1", (route) =>
    route.fulfill({
      json: {
        ...paths[0],
        evaluated_at: "2026-10-26T00:00:00Z",
        steps: [
          { index: 0, title: "Daromad", state: "practice_needed", prerequisites: [], required_recalls: 1, source_cards: 2, total_cards: 2, checkpoint_cards: 1, cards: [] },
          { index: 1, title: "Xulosa", state: "blocked_by_prerequisite", prerequisites: [0], required_recalls: 1, source_cards: 1, total_cards: 1, checkpoint_cards: 0, cards: [] },
        ],
        checkpoint_steps: 0,
        total_steps: 2,
        recommendations: [{ step: 0, action: "review_card", card_id: "c2", due_at: "2026-10-26T00:00:00Z", reason: "due_recall" }],
        action_authority: "none",
        mastery_claim: false,
      },
    }),
  );

  await page.goto("/student");
  await page.getByRole("button", { name: /Hisobot 2025/ }).click();
  await page.getByRole("button", { name: "Reja", exact: true }).click();
  const panel = page.getByTestId("learning-paths");
  await expect(panel).toContainText("Hali yo‘l yo‘q");
  await panel.getByLabel("Yangi yo‘l nomi").fill("Hisobot yo‘li");
  await panel.getByLabel("Qadam nomi 1").fill("Daromad");
  await panel.getByRole("button", { name: "Daromad 2025" }).click();
  await panel.getByRole("button", { name: "Daromad 2026" }).click();
  await panel.getByRole("button", { name: "Yo‘lni yaratish" }).click();
  await expect(panel.getByTestId("learning-path")).toContainText("Hisobot yo‘li");
  expect(created).toMatchObject({ title: "Hisobot yo‘li", language: "uz", steps: [{ title: "Daromad", card_ids: ["c1", "c2"], prerequisites: [], required_recalls: 1 }] });

  await panel.getByRole("button", { name: "Ochish" }).click();
  const detail = panel.getByTestId("learning-path-detail");
  await expect(detail).toContainText("0 / 2 qadam bajarildi");
  await expect(detail).toContainText("mashq kerak");
  await expect(detail).toContainText("oldingi qadam kutilmoqda");
  await expect(detail).toContainText("2/2 kartochka, 1 tasi eslangan");
  await expect(detail).toContainText("Kartochkani takrorlang: Daromad 2026");
  await expect(detail).toContainText("o‘zlashtirish da’vosi yo‘q");
});

test("student: a comparison cites every selected document or says the evidence was insufficient", async ({ page }) => {
  const requests: Record<string, unknown>[] = [];
  await page.route("**/api/student/status", (route) => route.fulfill({ json: { ai_provider_configured: true } }));
  await page.route("**/api/student/library?*", (route) => route.fulfill({ json: library }));
  await page.route("**/api/student/cards", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/student/progress", (route) => route.fulfill({ json: { active_cards: 0, due_cards: 0, review_events: 0, reviewed_cards: 0, assessment: "self_reported_recall" } }));
  await page.route("**/api/student/synthesize", (route) => {
    const body = route.request().postDataJSON() as Record<string, unknown>;
    requests.push(body);
    if (body.kind !== "comparison") return route.fulfill({ json: { status: "insufficient_evidence", generated: false, graph: null, citations: [] } });
    return route.fulfill({
      json: requests.length === 1
        ? { status: "generated", generated: true, text: "2025 daromadi 12% [1], 2026 daromadi 15% [2].", citations: [{ n: 1, excerpt: "12%", location: "p. 1" }, { n: 2, excerpt: "15%", location: "p. 1" }], provider: "fixture-mock" }
        : { status: "insufficient_evidence", generated: false, text: "Yetarli manba topilmadi.", citations: [], provider: null },
    });
  });

  await page.goto("/student");
  await page.getByRole("button", { name: /Hisobot 2025/ }).click();
  await page.getByRole("button", { name: "Tushunchalar", exact: true }).click();
  const panel = page.getByTestId("comparison");
  await panel.scrollIntoViewIfNeeded();
  await panel.getByRole("button", { name: "Taqqoslash" }).click();
  await expect(panel).toContainText("Kamida ikkita tayyor hujjat tanlang.");
  await panel.getByRole("button", { name: "Hisobot 2025" }).click();
  await panel.getByRole("button", { name: "Hisobot 2026" }).click();
  await panel.getByLabel("Savol").fill("Daromadni solishtir");
  await panel.getByRole("button", { name: "Taqqoslash" }).click();
  const result = panel.getByTestId("comparison-result");
  await expect(result).toContainText("2025 daromadi 12% [1]");
  await expect(result).toContainText("[2] p. 1");
  expect(requests[0]).toMatchObject({ document_ids: ["d1", "d2"], question: "Daromadni solishtir", kind: "comparison", language: "uz" });
  await panel.getByRole("button", { name: "Taqqoslash" }).click();
  await expect(result).toContainText("Yetarli manba topilmadi");
});
