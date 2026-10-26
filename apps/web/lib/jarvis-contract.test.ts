import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { dictionaries } from "@/lib/i18n/messages";
import {
  buildPercentageRequest,
  featureState,
  JARVIS_ENDPOINTS,
  parseCapabilities,
  parsePercentageResult,
  receiptShowsNoDelivery,
} from "./jarvis-contract";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const read = (relative: string) => readFileSync(path.join(REPO, relative), "utf8");

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    if (["node_modules", ".next", "tests"].includes(name)) continue;
    const full = path.join(dir, name);
    if (statSync(full).isDirectory()) walk(full, out);
    else if (/\.(ts|tsx|js|mjs|html|json)$/.test(name) && !/\.test\./.test(name)) out.push(full);
  }
  return out;
}

/** Routes declared by the CANONICAL backend (the single source of truth for this contract). */
function backendRoutes(): Set<string> {
  const source = read("apps/api/src/ezo_api/api/routes/jarvis.py");
  const prefix = /prefix="([^"]+)"/.exec(source)?.[1] ?? "";
  const routes = new Set<string>();
  for (const match of source.matchAll(/@router\.(get|post|put|patch|delete)\("([^"]*)"/g)) {
    routes.add(`${match[1].toUpperCase()} ${prefix}${match[2].replace(/\{[^}]+\}/g, "{}")}`);
  }
  return routes;
}

describe("backend contract (canonical Codex FastAPI routes)", () => {
  it("the canonical backend declares exactly the known JARVIS routes", () => {
    expect([...backendRoutes()].sort()).toEqual([
      "DELETE /api/jarvis/devices/{}",
      "GET /api/jarvis/capabilities",
      "GET /api/jarvis/devices",
      "GET /api/jarvis/devices/{}/work",
      "GET /api/jarvis/receipts/{}",
      "GET /api/jarvis/tasks",
      "GET /api/jarvis/tasks/{}",
      "GET /api/jarvis/telegram/recipients",
      "POST /api/jarvis/devices/pairing",
      "POST /api/jarvis/devices/{}/confirm",
      "POST /api/jarvis/devices/{}/results",
      "POST /api/jarvis/inspect-plan",
      "POST /api/jarvis/percentages",
      "POST /api/jarvis/tasks",
      "POST /api/jarvis/tasks/{}/cancel",
      "POST /api/jarvis/tasks/{}/retry",
      "POST /api/jarvis/tasks/{}/steps/{}/decision",
      "POST /api/jarvis/telegram/recipients",
      "POST /api/jarvis/telegram/recipients/{}/verify",
    ]);
  });

  it("every JARVIS path referenced by the web app or the extension exists in the backend", () => {
    const declared = new Set([...backendRoutes()].map((r) => r.split(" ")[1]));
    const files = [...walk(path.join(REPO, "apps/web")), ...walk(path.join(REPO, "apps/chrome-extension"))];
    const referenced: string[] = [];
    for (const file of files) {
      const text = readFileSync(file, "utf8");
      for (const match of text.matchAll(/\/api\/jarvis(?:[A-Za-z0-9_\-/.]|\$\{[^}]*\})*/g)) {
        referenced.push(match[0].replace(/\$\{[^}]*\}/g, "{}").replace(/\/+$/, ""));
      }
    }
    expect(referenced.length).toBeGreaterThan(0);
    for (const ref of referenced) expect(declared, `unsupported endpoint referenced: ${ref}`).toContain(ref);
  });

  it("no frontend or extension source references the removed fabricated endpoints", () => {
    // Still fabricated: none of these exist; tasks/cancel/decision are real routes now.
    const forbidden = /\/api\/jarvis\/(companion|plan\b|setup-scenario)|jarvis.*\/(execute|authorize)\b/;
    const files = [...walk(path.join(REPO, "apps/web")), ...walk(path.join(REPO, "apps/chrome-extension"))];
    for (const file of files) expect(readFileSync(file, "utf8"), file).not.toMatch(forbidden);
  });

  it("does not use credentialed fetch (backend CORS has allow_credentials=False)", () => {
    expect(read("apps/api/src/ezo_api/main.py")).toContain("allow_credentials=False");
    expect(read("apps/web/lib/jarvis-api.ts")).not.toContain('credentials: "include"');
  });

  it("the endpoint table matches the backend", () => {
    const declared = new Set([...backendRoutes()].map((r) => r.split(" ")[1]));
    expect(declared).toContain(JARVIS_ENDPOINTS.capabilities);
    expect(declared).toContain(JARVIS_ENDPOINTS.percentages);
    expect(declared).toContain(JARVIS_ENDPOINTS.inspectPlan);
    expect(declared).toContain("/api/jarvis/receipts/{}");
    expect(JARVIS_ENDPOINTS.receipt("a/b")).toBe("/api/jarvis/receipts/a%2Fb");
  });
});

describe("honest copy", () => {
  it("never claims paired/connected/delivered/completed in any language", () => {
    const claims = {
      en: /\b(paired|connected|delivered|completed|sent successfully)\b/i,
      uz: /\b(ulangan|juftlangan|yetkazildi|yuborildi|bajarildi|yakunlandi)\b/i,
      ru: /(подключен|сопряжен|доставлено|отправлено|выполнено|завершена)(?![а-яё])/i,
    } as const;
    for (const lang of ["en", "uz", "ru"] as const) {
      for (const [key, value] of Object.entries(dictionaries[lang].jarvis)) {
        expect(value, `${lang}.jarvis.${key}`).not.toMatch(claims[lang]);
      }
    }
  });

  it("the page source has no execute/approve/paired/delivered UI or fake fallback device", () => {
    const page = read("apps/web/components/pages/JarvisPage.tsx");
    for (const banned of ["Paired", "Yetkazildi", "awaiting_approval", "setup-scenario", "ezo-companion-win-01", "baxtiyor", "handleAuthorizeDecision"]) {
      expect(page).not.toContain(banned);
    }
  });
});

describe("capabilities parsing", () => {
  const body = {
    schema: "ezo-jarvis-capabilities-v1",
    tools: [{ name: "calculate_percentages", requires_confirmation: false, execution_authorized: false }],
    device_features: {
      windows_downloads: { available: false, missing_prerequisites: ["paired_windows_companion"], execution_authorized: false },
      telegram_send: { available: true, missing_prerequisites: [], execution_authorized: false },
    },
    trust: "tool_metadata_is_not_action_authorization",
  };

  it("accepts the real backend shape", () => {
    expect(parseCapabilities(body)?.device_features.windows_downloads.missing_prerequisites).toEqual(["paired_windows_companion"]);
  });

  it("rejects wrong schema or malformed features instead of guessing", () => {
    expect(parseCapabilities({ ...body, schema: "other" })).toBeNull();
    expect(parseCapabilities({ ...body, device_features: { x: { available: "yes" } } })).toBeNull();
    expect(parseCapabilities(null)).toBeNull();
  });

  it("never reports operational unless the backend authorizes execution", () => {
    const caps = parseCapabilities(body)!;
    expect(featureState(caps.device_features.windows_downloads)).toBe("not_available");
    expect(featureState(caps.device_features.telegram_send)).toBe("prerequisites_reported_execution_not_authorized");
  });
});

describe("percentage contract", () => {
  it("builds a request exactly as the backend schema expects", () => {
    const built = buildPercentageRequest("percent_change", [{ previous: "100", current: "125.5" }], 2);
    expect(built).toEqual({
      ok: true,
      body: { method: "percent_change", pairs: [{ id: "row1", previous: "100", current: "125.5" }], decimal_places: 2 },
    });
  });

  it("rejects what the backend rejects: zero base, expressions, exponents, bad precision, empty", () => {
    expect(buildPercentageRequest("percent_of", [{ previous: "0", current: "5" }], 2)).toMatchObject({ ok: false });
    expect(buildPercentageRequest("percent_of", [{ previous: "1e3", current: "5" }], 2)).toMatchObject({ ok: false });
    expect(buildPercentageRequest("percent_of", [{ previous: "1+1", current: "5" }], 2)).toMatchObject({ ok: false });
    expect(buildPercentageRequest("percent_of", [{ previous: "1", current: "5" }], 9)).toMatchObject({ ok: false });
    expect(buildPercentageRequest("percent_of", [], 2)).toMatchObject({ ok: false });
  });

  const response = {
    method: "percent_change",
    formula: "(current-previous)/previous*100",
    rounding: "ROUND_HALF_EVEN",
    decimal_places: 2,
    provenance: "caller_supplied_values_not_document_extraction",
    results: [{ id: "row1", previous: "100", current: "125", result_percent: "25.00" }],
    receipt: {
      id: "11111111-1111-4111-8111-111111111111",
      schema: "ezo-execution-receipt-v1",
      step_type: "tool_call",
      tool: "calculate_percentages",
      outcome: "completed_deterministic_calculation",
      input_sha256: "a",
      output_sha256: "b",
      duration_ms: 1,
      external_delivery: "not_attempted",
    },
  };

  it("parses a real response and surfaces that nothing was delivered", () => {
    const parsed = parsePercentageResult(response)!;
    expect(parsed.results[0].result_percent).toBe("25.00");
    expect(receiptShowsNoDelivery(parsed.receipt)).toBe(true);
  });

  it("rejects responses without a valid receipt or with wrong types", () => {
    expect(parsePercentageResult({ ...response, receipt: undefined })).toBeNull();
    expect(parsePercentageResult({ ...response, results: [{ id: 1 }] })).toBeNull();
    expect(parsePercentageResult({ ...response, receipt: { ...response.receipt, schema: "x" } })).toBeNull();
  });
});
