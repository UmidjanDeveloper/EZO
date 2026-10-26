import type { AgentRun } from "@ezo/shared";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { AgentWeb } from "./AgentWeb";

const run: AgentRun = {
  id: "r1",
  conversation_id: null,
  status: "completed",
  intent: "research",
  intent_confidence: 0.9,
  agent: "student",
  language: "uz",
  route: "fast",
  provider: "openai",
  model: "gpt",
  latency_ms: 1200,
  input_tokens: 10,
  output_tokens: 20,
  steps: [
    { name: "web_search", status: "ok", duration_ms: 300, summary: "3 results" },
    { name: "read_source", status: "error", duration_ms: 50, summary: "timeout" },
  ],
  attempts: [{ provider: "openai", model: "gpt", status: "ok", latency_ms: 800, error_kind: null, error: null }],
  tool_calls: [],
  error: null,
  created_at: "2026-10-26T00:00:00Z",
  finished_at: "2026-10-26T00:00:02Z",
};

describe("AgentWeb", () => {
  it("draws only what the trace recorded: the agent, the route and each step, lit by its outcome", () => {
    const html = renderToStaticMarkup(<AgentWeb run={run} />);
    expect(html).toContain('data-nodes="4"');
    expect(html).toContain(">student<");
    expect(html).toContain(">openai/gpt<");
    expect(html).toContain(">web_search<");
    expect((html.match(/data-ok="false"/g) ?? []).length).toBe(1); // the failed step only
    expect(html).toContain('aria-hidden="true"');
  });

  it("shows an empty constellation for a run with no steps or provider", () => {
    const html = renderToStaticMarkup(<AgentWeb run={{ ...run, agent: null, provider: null, steps: [], attempts: [] }} />);
    expect(html).toContain('data-nodes="0"');
    expect(html).toContain(">EZO<");
  });
});
