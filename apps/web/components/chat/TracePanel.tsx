"use client";

import { Badge, Spinner } from "@ezo/ui";
import { AnimatePresence, motion } from "framer-motion";
import { X } from "lucide-react";
import { useCallback } from "react";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n/context";
import { useApiData } from "@/lib/use-api-data";

export function TracePanel({ runId, onClose }: { runId: string | null; onClose: () => void }) {
  const { m } = useI18n();
  return (
    <AnimatePresence>
      {runId ? (
        <motion.aside
          className="fixed inset-y-0 right-0 z-50 flex w-full max-w-md flex-col border-l border-line bg-surface shadow-2xl"
          initial={{ x: "100%" }}
          animate={{ x: 0 }}
          exit={{ x: "100%" }}
          transition={{ type: "tween", duration: 0.2 }}
          data-testid="trace-panel"
        >
          <header className="flex items-center justify-between border-b border-line px-4 py-3">
            <h2 className="font-semibold">{m.trace.title}</h2>
            <button type="button" onClick={onClose} className="rounded p-1 text-ink-muted hover:text-ink" aria-label={m.common.close}>
              <X size={18} />
            </button>
          </header>
          <TraceBody key={runId} runId={runId} />
        </motion.aside>
      ) : null}
    </AnimatePresence>
  );
}

function TraceBody({ runId }: { runId: string }) {
  const { m } = useI18n();
  const { data: run, error: loadError } = useApiData(useCallback(() => api.getAgentRun(runId), [runId]));
  const error = loadError?.message;
  return (
          <div className="flex-1 overflow-y-auto p-4 text-sm">
            {error ? <p className="text-danger">{error}</p> : null}
            {!run && !error ? <Spinner label={m.common.loading} /> : null}
            {run ? (
              <div className="flex flex-col gap-5">
                <dl className="grid grid-cols-2 gap-x-4 gap-y-2">
                  <Row label={m.trace.intent} value={`${run.intent} (${run.intent_confidence ?? "–"})`} />
                  <Row label={m.trace.agent} value={run.agent} />
                  <Row label={m.trace.route} value={run.route} />
                  <Row label={m.trace.model} value={run.provider ? `${run.provider}/${run.model}` : null} />
                  <Row label={m.trace.latency} value={run.latency_ms != null ? `${run.latency_ms} ms` : null} />
                  <Row
                    label={m.trace.tokens}
                    value={run.input_tokens != null ? `${run.input_tokens} → ${run.output_tokens}` : null}
                  />
                </dl>
                <section>
                  <h3 className="mb-2 font-medium">{m.trace.steps}</h3>
                  <ol className="flex flex-col gap-1.5">
                    {run.steps.map((step, index) => (
                      <li key={`${step.name}-${index}`} className="rounded-lg border border-line bg-surface-2 px-3 py-2">
                        <div className="flex items-center justify-between gap-2">
                          <span className="font-mono text-xs">{step.name}</span>
                          <span className="text-xs text-ink-faint">{step.duration_ms} ms</span>
                        </div>
                        {step.summary ? <p className="mt-1 break-words text-xs text-ink-muted">{step.summary}</p> : null}
                      </li>
                    ))}
                  </ol>
                </section>
                <section>
                  <h3 className="mb-2 font-medium">{m.trace.attempts}</h3>
                  <ul className="flex flex-col gap-1.5">
                    {run.attempts.map((attempt, index) => (
                      <li key={index} className="flex flex-wrap items-center gap-2 text-xs">
                        <Badge tone={attempt.status === "ok" ? "success" : "danger"}>{attempt.status}</Badge>
                        <span className="font-mono">
                          {attempt.provider}/{attempt.model}
                        </span>
                        <span className="text-ink-faint">{attempt.latency_ms} ms</span>
                        {attempt.error_kind ? <span className="text-danger">{attempt.error_kind}</span> : null}
                      </li>
                    ))}
                  </ul>
                </section>
                {run.error ? <p className="break-words text-xs text-danger">{run.error}</p> : null}
                <p className="text-xs text-ink-faint">{m.trace.note}</p>
              </div>
            ) : null}
          </div>
  );
}

function Row({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <>
      <dt className="text-ink-muted">{label}</dt>
      <dd className="break-words font-mono text-xs leading-5">{value ?? "–"}</dd>
    </>
  );
}
