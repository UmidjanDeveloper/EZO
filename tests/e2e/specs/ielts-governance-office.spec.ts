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
        fluency_score: 7.0,
        lexical_score: 6.5,
        grammar_score: 7.0,
        pronunciation_score: 7.0,
        estimated_band_low: 6.5,
        estimated_band_high: 7.0,
        estimated_band: 7.0,
        constructive_feedback: "Good natural fluency and varied vocabulary.",
        explanation_uz: "Ravonlik yaxshi, grammatik xatolar deyarli uchramadi.",
        disclaimer: "Ushbu baho norasmiy baholash hisoblanadi (Estimated Band Score) va rasmiy IELTS sertifikati o'rnini bosmaydi.",
      },
    })
  );

  await page.route("**/api/ielts/sessions/sess-test-01/advance", (route) =>
    route.fulfill({
      json: {
        next_prompt: "What do you like most about your hometown?",
        part: 1,
        finished: false,
        feedback: "Clear pronunciation and fluent pace.",
        explanation_uz: "Talaffuz aniq va nutq sur'ati me'yorda.",
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
        feedback: "Clear pronunciation and fluent pace.",
      },
    })
  );

  await page.goto("/ielts");
  await expect(page.getByRole("heading", { level: 1, name: /IELTS Speaking/ })).toBeVisible();

  // Stats bar visible
  await expect(page.getByText("Sinovlar soni")).toBeVisible();
  await expect(page.getByText("3")).toBeVisible();

  // Start new test session
  await page.getByRole("button", { name: "Imtihonni boshlash" }).click();

  // Examiner prompt displayed
  await expect(page.getByText("Could you tell me your full name and where you are from?")).toBeVisible();

  // Type answer and submit
  await page.getByLabel("Sizning javobingiz:").fill("My name is Umidjan and I am from Tashkent, Uzbekistan.");
  await page.getByRole("button", { name: "Yuborish" }).click();

  // Check advance and feedback
  await expect(page.getByText("What do you like most about your hometown?")).toBeVisible();
  await expect(page.getByText("Clear pronunciation and fluent pace.")).toBeVisible();
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
  await expect(page.getByText("Ruxsat berilmagan (403 Forbidden)")).toBeVisible();
  await expect(page.getByText("Obuna darajasi (Pro, Enterprise) platforma boshqaruv huquqini bermaydi.")).toBeVisible();
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

  await page.route("**/api/admin/governance/system-health", (route) =>
    route.fulfill({
      json: {
        status: "healthy",
        uptime_seconds: 259200,
        db_status: "connected",
        worker_status: "active",
        memory_usage_mb: 148.5,
        api_version: "0.2.0-master",
        active_sessions: 14,
      },
    })
  );

  await page.route("**/api/admin/governance/agents", (route) =>
    route.fulfill({
      json: [
        {
          agent_id: "student",
          name: "EZO Student",
          description: "Manba asosida o'rganish",
          model: "stored-normalized-text/v1",
          max_tokens: 4096,
          temperature: 0.2,
          rate_limit_per_min: 60,
          enabled: true,
          allowed_roles: ["user", "super_admin"],
        },
      ],
    })
  );

  await page.route("**/api/admin/governance/proposals", (route) =>
    route.fulfill({
      json: [
        {
          id: "prop-001",
          title: "Upgrade Student durable parser to isolated worker pool v2",
          description: "Isolate untrusted document extraction into non-root ephemeral containers.",
          category: "security_isolation",
          status: "pending",
          proposed_by: "system_audit",
          created_at: "2026-10-21T09:00:00Z",
          review_notes: null,
        },
      ],
    })
  );

  await page.route("**/api/admin/governance/audit-logs", (route) =>
    route.fulfill({
      json: [
        {
          id: "audit-101",
          timestamp: "2026-10-22T10:00:00Z",
          user_identifier: "admin@ezo.internal",
          action: "GOVERNANCE_STATUS_INSPECT",
          resource: "/api/admin/governance/status",
          status: "SUCCESS",
          ip_masked: "127.0.0.***",
        },
      ],
    })
  );

  await page.route("**/api/admin/governance/budgets", (route) =>
    route.fulfill({
      json: {
        daily_token_budget: 1000000,
        tokens_consumed_today: 142350,
        monthly_spend_limit_usd: 250.0,
        current_spend_usd: 38.45,
        storage_quota_mb: 10000,
        storage_used_mb: 1420,
      },
    })
  );

  await page.goto("/admin");
  await expect(page.getByText("Super Admin: Autentifikatsiya Tasdiqlangan")).toBeVisible();
  await expect(page.getByText("Tizim salomatligi")).toBeVisible();
  await expect(page.getByText("EZO Student")).toBeVisible();
  await expect(page.getByText("Upgrade Student durable parser")).toBeVisible();
});

test("office: presentation maker and document workspace", async ({ page }) => {
  await page.goto("/presentations");
  await expect(page.getByRole("heading", { level: 1, name: /Taqdimotlar/ })).toBeVisible();
  await expect(page.getByLabel("Taqdimot mavzusi")).toBeVisible();

  await page.goto("/office");
  await expect(page.getByRole("heading", { level: 1, name: /Hujjatlar va Ofis/ })).toBeVisible();
  await expect(page.getByText("Makroslar va tashqi skriptlarsiz toza, xavfsiz ofis fayllari yaratiladi.")).toBeVisible();
});
