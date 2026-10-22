import { expect, test } from "@playwright/test";

test("ielts: interactive speaking workflow, criteria evaluation and disclaimer", async ({ page }) => {
  await page.route("**/api/ielts/cue-cards", (route) =>
    route.fulfill({
      json: [
        {
          id: "cc-hometown",
          task: "Describe your hometown",
          points: ["Where it is located", "What you like most about it", "How it has changed"],
          follow_up: "Do you think you will continue living there?",
          discussion: ["Urbanization in developing nations"],
        },
      ],
    })
  );

  await page.route("**/api/ielts/voice-status", (route) =>
    route.fulfill({
      json: {
        available: true,
        provider: "elevenlabs",
        fallback_mode: "browser_and_text_fallback",
        notice_uz: "Ovozli xizmat (ElevenLabs) faol.",
        notice_en: "Voice service active.",
      },
    })
  );

  await page.route("**/api/ielts/stats", (route) =>
    route.fulfill({
      json: {
        total_sessions: 3,
        completed_sessions: 2,
        average_band: 6.5,
        best_band: 7.0,
        total_speaking_minutes: 25,
        common_mistakes: ["Subject-verb agreement", "Tense consistency"],
      },
    })
  );

  await page.route("**/api/ielts/sessions", (route) =>
    route.fulfill({
      json: {
        id: "sess-test-01",
        status: "in_progress",
        ielts_part: 1,
        cue_card: null,
        current_prompt: "Could you tell me your full name and where you are from?",
        answered_count: 0,
        finished: false,
        band_low: null,
        band_high: null,
        feedback: null,
      },
    })
  );

  await page.route("**/api/ielts/evaluate", (route) =>
    route.fulfill({
      json: {
        fluency_score: null,
        lexical_score: null,
        grammar_score: null,
        pronunciation_score: null,
        estimated_band_low: null,
        estimated_band_high: null,
        estimated_band: null,
        constructive_feedback: "Answer length: 11 words. No AI assessment was performed.",
        explanation_uz: "Javobda 11 ta so'z bor. AI va talaffuz baholashi bajarilmagan.",
        disclaimer: "Rasmiy IELTS sertifikati emas. Text practice only.",
      },
    })
  );

  await page.route("**/api/ielts/sessions/sess-test-01/advance", (route) =>
    route.fulfill({
      json: {
        session_id: "sess-test-01",
        part: 1,
        instruction: "Davom eting",
        finished: false,
        feedback: "Matnli mashq bajarildi.",
        explanation_uz: "Keyingi savolga o'ting.",
      },
    })
  );

  await page.route("**/api/ielts/sessions/sess-test-01", (route) =>
    route.fulfill({
      json: {
        id: "sess-test-01",
        status: "in_progress",
        ielts_part: 1,
        cue_card: null,
        current_prompt: "What do you like most about your hometown?",
        answered_count: 1,
        finished: false,
        band_low: null,
        band_high: null,
        feedback: "Matnli mashq bajarildi.",
      },
    })
  );

  await page.goto("/ielts");
  await expect(page.getByRole("heading", { level: 1, name: /IELTS Speaking/ })).toBeVisible();

  // Stats bar visible
  await expect(page.getByText("Sinovlar soni")).toBeVisible();
  await expect(page.getByText("3")).toBeVisible();

  // Start new test session
  await page.getByRole("button", { name: /Yangi imtihon/i }).click();

  // Examiner prompt displayed
  await expect(page.getByText("Could you tell me your full name and where you are from?")).toBeVisible();

  // Type answer and submit
  await page.getByLabel("Sizning javobingiz:").fill("My name is Umidjan and I am from Tashkent, Uzbekistan.");
  await page.getByRole("button", { name: "Yuborish" }).click();

  // Check advance
  await expect(page.getByText("What do you like most about your hometown?")).toBeVisible();
});

test("governance: ordinary user receives 403 Forbidden with RBAC warning", async ({ page }) => {
  await page.route("**/api/admin/governance/status", (route) =>
    route.fulfill({
      status: 403,
      json: {
        error: {
          code: "forbidden",
          message: "Super Admin privileges required. Subscription status does not grant governance access.",
        },
      },
    })
  );

  await page.goto("/admin");
  await expect(page.getByText("Kirish taqiqlangan (403 Forbidden)")).toBeVisible();
  await expect(page.getByText("Obuna maqomi (pro, enterprise) platforma boshqaruviga ruxsat bermaydi.")).toBeVisible();
});

test("governance: super admin accesses health, agent routing, proposals, and audit logs", async ({ page }) => {
  await page.route("**/api/admin/governance/status", (route) =>
    route.fulfill({
      json: {
        role: "super_admin",
        super_admin_verified: true,
        autonomous_code_modification: false,
        autonomous_pr_merge: false,
        autonomous_deployment: false,
        governance_mode: "human_governed",
        policies: {
          tenant_isolation: "enforced",
          memory_opt_in: "enforced",
          subscription_privilege_escalation: "blocked",
          k8_autonomous_modification: "disabled",
        },
      },
    })
  );

  await page.route("**/api/status", (route) =>
    route.fulfill({
      json: {
        deployment_profile: "full",
        disabled_capabilities: [],
        version: "0.2.0",
        environment: "development",
        database: "postgresql",
        offline_mode: false,
        providers: [{ name: "openai", display_name: "OpenAI", configured: true, capabilities: ["chat"] }],
        routing: {},
        agents: [
          {
            key: "student",
            names: { uz: "EZO Student" },
            description: "Manba asosida o'rganish",
            available: true,
            maturity: "v1",
            phase: "stable",
          },
        ],
        debug_traces: true,
      },
    })
  );

  await page.route("**/api/health", (route) =>
    route.fulfill({
      json: {
        status: "ok",
        database: "ok",
      },
    })
  );

  await page.route("**/api/admin/governance/improvements", (route) =>
    route.fulfill({
      json: [
        {
          id: "prop-001",
          sha256: "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
          goal: "Upgrade Student durable parser to isolated worker pool v2",
          status: "proposal_only",
          sandbox_tested: false,
          execution_authorized: false,
        },
      ],
    })
  );

  await page.goto("/admin");
  await expect(page.getByText("Super Admin Autentifikatsiya Qilingan")).toBeVisible();
  await expect(page.getByText("Ro‘yxatdan o‘tgan Agentlar katalogi")).toBeVisible();
  await expect(page.getByText("EZO Student")).toBeVisible();
  await expect(page.getByText("Upgrade Student durable parser to isolated worker pool v2")).toBeVisible();
});

test("office: presentation maker and document workspace", async ({ page }) => {
  await page.goto("/presentations");
  await expect(page.getByRole("heading", { level: 1, name: /Taqdimotlar/ })).toBeVisible();
  await expect(page.getByLabel("Taqdimot mavzusi")).toBeVisible();

  await page.goto("/office");
  await expect(page.getByRole("heading", { level: 1, name: /Hujjatlar va Ofis/ })).toBeVisible();
  await expect(page.getByText("Makroslar va tashqi skriptlarsiz toza, xavfsiz ofis fayllari yaratiladi.")).toBeVisible();
});
