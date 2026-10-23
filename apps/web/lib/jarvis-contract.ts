/**
 * Client-side mirror of the CANONICAL backend JARVIS contract
 * (apps/api/src/ezo_api/api/routes/jarvis.py, docs/integration/MASTER_API_CONTRACT.md).
 *
 * The backend exposes exactly four JARVIS routes. None of them plans, executes,
 * pairs a device, reads a file, makes a PDF or sends a Telegram message. This module
 * therefore only models those four routes. Do not add endpoints here until the
 * canonical backend (Codex/Claude) ships and documents them; `jarvis-contract.test.ts`
 * fails if the frontend references a route the backend does not declare.
 */

export const JARVIS_ENDPOINTS = {
  capabilities: "/api/jarvis/capabilities",
  percentages: "/api/jarvis/percentages",
  inspectPlan: "/api/jarvis/inspect-plan",
  receipt: (id: string) => `/api/jarvis/receipts/${encodeURIComponent(id)}`,
} as const;

/** Mirrors `availability()` in orchestration/planning_policy.py. */
export interface DeviceFeature {
  available: boolean;
  missing_prerequisites: string[];
  execution_authorized: boolean;
}

export interface Capabilities {
  schema: string;
  tools: Array<{ name: string; requires_confirmation: boolean; execution_authorized: boolean }>;
  device_features: Record<string, DeviceFeature>;
  trust: string;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function parseFeature(value: unknown): DeviceFeature | null {
  if (!isRecord(value)) return null;
  const { available, missing_prerequisites: missing, execution_authorized: auth } = value;
  if (typeof available !== "boolean" || typeof auth !== "boolean") return null;
  if (!Array.isArray(missing) || !missing.every((item) => typeof item === "string")) return null;
  return { available, missing_prerequisites: missing as string[], execution_authorized: auth };
}

/** Strictly validates a /capabilities body. Anything unexpected returns null (never a guess). */
export function parseCapabilities(raw: unknown): Capabilities | null {
  if (!isRecord(raw) || raw.schema !== "ezo-jarvis-capabilities-v1") return null;
  if (!Array.isArray(raw.tools) || !isRecord(raw.device_features)) return null;
  const tools: Capabilities["tools"] = [];
  for (const tool of raw.tools) {
    if (!isRecord(tool) || typeof tool.name !== "string") return null;
    tools.push({
      name: tool.name,
      requires_confirmation: tool.requires_confirmation === true,
      execution_authorized: tool.execution_authorized === true,
    });
  }
  const features: Record<string, DeviceFeature> = {};
  for (const [name, value] of Object.entries(raw.device_features)) {
    const feature = parseFeature(value);
    if (!feature) return null;
    features[name] = feature;
  }
  return {
    schema: raw.schema,
    tools,
    device_features: features,
    trust: typeof raw.trust === "string" ? raw.trust : "",
  };
}

/**
 * What the UI may say about a device feature. Even when the backend reports every
 * prerequisite as met, `execution_authorized` is false on this route, so a feature can
 * never be shown as operational, connected, paired or delivered from this contract.
 */
export type FeatureState = "not_available" | "prerequisites_reported_execution_not_authorized" | "authorized_by_backend";

export function featureState(feature: DeviceFeature): FeatureState {
  if (!feature.available) return "not_available";
  return feature.execution_authorized ? "authorized_by_backend" : "prerequisites_reported_execution_not_authorized";
}

// --- percentages ---------------------------------------------------------------------

/** Same grammar as NUMBER in apps/api/src/ezo_api/tools/percentage.py. */
export const DECIMAL_PATTERN = /^-?(?:0|[1-9][0-9]{0,17})(?:\.[0-9]{1,12})?$/;
export const MAX_PAIRS = 50;

export type PercentageMethod = "percent_change" | "percent_of";

export interface PercentageRowInput {
  previous: string;
  current: string;
}

export interface PercentageRequest {
  method: PercentageMethod;
  pairs: Array<{ id: string; previous: string; current: string }>;
  decimal_places: number;
}

export type BuildResult = { ok: true; body: PercentageRequest } | { ok: false; error: string };

/** Validates exactly what the backend validates, so the UI never sends a request it knows is invalid. */
export function buildPercentageRequest(
  method: PercentageMethod,
  rows: PercentageRowInput[],
  decimalPlaces: number,
): BuildResult {
  if (rows.length < 1 || rows.length > MAX_PAIRS) return { ok: false, error: "rows_count" };
  if (!Number.isInteger(decimalPlaces) || decimalPlaces < 0 || decimalPlaces > 8) {
    return { ok: false, error: "decimal_places" };
  }
  const pairs: PercentageRequest["pairs"] = [];
  for (const [index, row] of rows.entries()) {
    const previous = row.previous.trim();
    const current = row.current.trim();
    if (previous.length > 32 || current.length > 32) return { ok: false, error: `row_${index + 1}_format` };
    if (!DECIMAL_PATTERN.test(previous) || !DECIMAL_PATTERN.test(current)) {
      return { ok: false, error: `row_${index + 1}_format` };
    }
    if (Number(previous) === 0) return { ok: false, error: `row_${index + 1}_zero_previous` };
    pairs.push({ id: `row${index + 1}`, previous, current });
  }
  return { ok: true, body: { method, pairs, decimal_places: decimalPlaces } };
}

export interface CalculationReceipt {
  id: string;
  schema: string;
  outcome: string;
  tool: string;
  input_sha256: string;
  output_sha256: string;
  duration_ms: number;
  external_delivery: string;
}

export interface PercentageResult {
  method: PercentageMethod;
  formula: string;
  rounding: string;
  decimal_places: number;
  provenance: string;
  results: Array<{ id: string; previous: string; current: string; result_percent: string }>;
  receipt: CalculationReceipt;
}

/** Returns null unless the body is a complete, schema-correct /percentages response. */
export function parsePercentageResult(raw: unknown): PercentageResult | null {
  if (!isRecord(raw) || !Array.isArray(raw.results) || !isRecord(raw.receipt)) return null;
  if (raw.method !== "percent_change" && raw.method !== "percent_of") return null;
  const receipt = raw.receipt;
  if (receipt.schema !== "ezo-execution-receipt-v1" || typeof receipt.id !== "string") return null;
  if (typeof receipt.outcome !== "string" || typeof receipt.external_delivery !== "string") return null;
  const results: PercentageResult["results"] = [];
  for (const item of raw.results) {
    if (!isRecord(item)) return null;
    const { id, previous, current, result_percent: value } = item;
    if (![id, previous, current, value].every((field) => typeof field === "string")) return null;
    results.push({ id: id as string, previous: previous as string, current: current as string, result_percent: value as string });
  }
  return {
    method: raw.method,
    formula: typeof raw.formula === "string" ? raw.formula : "",
    rounding: typeof raw.rounding === "string" ? raw.rounding : "",
    decimal_places: typeof raw.decimal_places === "number" ? raw.decimal_places : 0,
    provenance: typeof raw.provenance === "string" ? raw.provenance : "",
    results,
    receipt: {
      id: receipt.id,
      schema: receipt.schema,
      outcome: receipt.outcome,
      tool: typeof receipt.tool === "string" ? receipt.tool : "",
      input_sha256: typeof receipt.input_sha256 === "string" ? receipt.input_sha256 : "",
      output_sha256: typeof receipt.output_sha256 === "string" ? receipt.output_sha256 : "",
      duration_ms: typeof receipt.duration_ms === "number" ? receipt.duration_ms : 0,
      external_delivery: receipt.external_delivery,
    },
  };
}

/** True only when the backend itself states that nothing external was attempted. */
export function receiptShowsNoDelivery(receipt: CalculationReceipt): boolean {
  return receipt.external_delivery === "not_attempted";
}
