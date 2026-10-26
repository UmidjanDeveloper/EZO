"use client";

import { Button, Card, cn, Spinner } from "@ezo/ui";
import { Check, Link2, Monitor, Play, RotateCcw, Send, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useI18n } from "@/lib/i18n/context";
import {
  jarvisCall,
  JarvisCallError,
  type JarvisDevice,
  type JarvisRecipient,
  type JarvisStep,
  type JarvisTask,
} from "@/lib/jarvis-api";
import type { Section as JarvisConsoleTexts } from "@/lib/i18n/sections/jarvisConsole";

/**
 * JARVIS owner console: pair devices with the code shown on the device, link Telegram
 * recipients (they press Start in EZO's bot), start document tasks and approve the
 * EXACT external action shown. Every status comes from the API; nothing is assumed.
 */
const INPUT =
  "w-full rounded-lg border border-line bg-surface-raised px-3 py-2 text-sm text-ink outline-none focus:border-accent focus:ring-1 focus:ring-accent";

function stepLabels(t: JarvisConsoleTexts): Record<string, string> {
  return {
    "files.latest_documents": t.steps.filesLatestDocuments,
    "document.extract": t.steps.documentExtract,
    "compute.percentages": t.steps.computePercentages,
    "document.convert_pdf": t.steps.documentConvertPdf,
    "document.report_pdf": t.steps.documentReportPdf,
    "telegram.send": t.steps.telegramSend,
  };
}

function stateLabels(t: JarvisConsoleTexts): Record<string, string> {
  return {
    queued: t.states.queued,
    pending: t.states.pending,
    running: t.states.running,
    awaiting_device: t.states.awaitingDevice,
    awaiting_authorization: t.states.awaitingAuthorization,
    completed: t.states.completed,
    failed: t.states.failed,
    cancelled: t.states.cancelled,
  };
}

function message(error: unknown, fallback: string): string {
  if (error instanceof JarvisCallError) return error.message;
  return fallback;
}

export function JarvisConsole() {
  const { m } = useI18n();
  const fallback = m.jarvisConsole.serverUnreachable;
  const [devices, setDevices] = useState<JarvisDevice[] | null>(null);
  const [recipients, setRecipients] = useState<JarvisRecipient[]>([]);
  const [tasks, setTasks] = useState<JarvisTask[]>([]);
  const [error, setError] = useState<string | null>(null);

  const [tick, setTick] = useState(0);
  const reload = useCallback(() => setTick((n) => n + 1), []);

  useEffect(() => {
    let alive = true;
    Promise.all([
      jarvisCall<JarvisDevice[]>("/api/jarvis/devices"),
      jarvisCall<JarvisRecipient[]>("/api/jarvis/telegram/recipients"),
      jarvisCall<JarvisTask[]>("/api/jarvis/tasks"),
    ])
      .then(([d, r, t]) => {
        if (!alive) return;
        setDevices(d);
        setRecipients(r);
        setTasks(t);
        setError(null);
      })
      .catch((err: unknown) => alive && setError(message(err, fallback)));
    return () => {
      alive = false;
    };
  }, [tick, fallback]);

  useEffect(() => {
    // Running tasks change on the server (device answers, worker steps): refresh gently.
    const timer = setInterval(reload, 5000);
    return () => clearInterval(timer);
  }, [reload]);

  const act = async (fn: () => Promise<unknown>) => {
    try {
      await fn();
      reload();
    } catch (err) {
      setError(message(err, fallback));
    }
  };

  return (
    <div className="space-y-6" data-testid="jarvis-console">
      {error && (
        <p role="alert" className="rounded-lg border border-red-500/40 bg-red-500/5 px-3 py-2 text-sm text-red-600">
          {error}
        </p>
      )}
      <Devices devices={devices} act={act} />
      <Recipients recipients={recipients} act={act} />
      <NewTask act={act} />
      <Tasks tasks={tasks} act={act} />
    </div>
  );
}

type Act = (fn: () => Promise<unknown>) => Promise<void>;

function Devices({ devices, act }: { devices: JarvisDevice[] | null; act: Act }) {
  const { m } = useI18n();
  const t = m.jarvisConsole.devices;
  const [codes, setCodes] = useState<Record<string, string>>({});
  return (
    <Card className="p-5" data-testid="jarvis-devices">
      <h2 className="mb-1 flex items-center gap-2 text-sm font-semibold text-ink">
        <Monitor className="h-4 w-4" aria-hidden /> {t.title}
      </h2>
      <p className="mb-3 text-xs text-ink-muted">{t.hint}</p>
      {devices === null ? (
        <Spinner />
      ) : devices.length === 0 ? (
        <p className="text-sm text-ink-muted">{t.empty}</p>
      ) : (
        <ul className="space-y-2">
          {devices.map((d) => (
            <li key={d.id} className="flex flex-wrap items-center gap-2 text-sm">
              <span className="font-medium text-ink">{d.name}</span>
              <span className={cn("rounded px-1.5 text-xs", d.status === "paired" ? "bg-emerald-500/10 text-emerald-600" : "bg-amber-500/10 text-amber-600")}>
                {d.status === "paired" ? t.statusPaired : d.status === "pending" ? t.statusPending : t.statusRevoked}
              </span>
              {d.status === "pending" && (
                <>
                  <input
                    aria-label={t.codeLabel}
                    inputMode="numeric"
                    maxLength={6}
                    className={cn(INPUT, "w-28")}
                    value={codes[d.id] ?? ""}
                    onChange={(e) => setCodes({ ...codes, [d.id]: e.target.value.replace(/\D/g, "") })}
                  />
                  <Button size="sm" onClick={() => void act(() => jarvisCall(`/api/jarvis/devices/${d.id}/confirm`, { method: "POST", body: { code: codes[d.id] ?? "" } }))}>
                    {t.confirm}
                  </Button>
                </>
              )}
              {d.status !== "revoked" && (
                <Button size="sm" variant="secondary" onClick={() => void act(() => jarvisCall(`/api/jarvis/devices/${d.id}`, { method: "DELETE" }))}>
                  {t.revoke}
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function Recipients({ recipients, act }: { recipients: JarvisRecipient[]; act: Act }) {
  const { m } = useI18n();
  const t = m.jarvisConsole.recipients;
  const [label, setLabel] = useState("");
  const [pending, setPending] = useState<Record<string, { code: string; link: string }>>({});
  return (
    <Card className="p-5" data-testid="jarvis-recipients">
      <h2 className="mb-1 flex items-center gap-2 text-sm font-semibold text-ink">
        <Link2 className="h-4 w-4" aria-hidden /> {t.title}
      </h2>
      <p className="mb-3 text-xs text-ink-muted">{t.hint}</p>
      <div className="mb-3 flex gap-2">
        <input aria-label={t.nameLabel} placeholder={t.namePlaceholder} className={INPUT} value={label} onChange={(e) => setLabel(e.target.value)} />
        <Button
          size="sm"
          disabled={label.trim().length < 2}
          onClick={() =>
            void act(async () => {
              const created = await jarvisCall<{ recipient: JarvisRecipient; code: string; link: string }>("/api/jarvis/telegram/recipients", {
                method: "POST",
                body: { label: label.trim() },
              });
              setPending({ ...pending, [created.recipient.id]: { code: created.code, link: created.link } });
              setLabel("");
            })
          }
        >
          {t.add}
        </Button>
      </div>
      <ul className="space-y-2">
        {recipients.map((r) => (
          <li key={r.id} className="text-sm">
            <span className="font-medium text-ink">{r.label}</span>{" "}
            {r.status === "verified" ? (
              <span className="text-xs text-emerald-600">{t.linked}{r.telegram_name ? ` (${r.telegram_name})` : ""}</span>
            ) : pending[r.id] ? (
              <span className="inline-flex flex-wrap items-center gap-2">
                <a className="text-xs text-accent underline" href={pending[r.id]!.link} target="_blank" rel="noreferrer">
                  {pending[r.id]!.link}
                </a>
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => void act(() => jarvisCall(`/api/jarvis/telegram/recipients/${r.id}/verify`, { method: "POST", body: { code: pending[r.id]!.code } }))}
                >
                  {t.verify}
                </Button>
              </span>
            ) : (
              <span className="text-xs text-amber-600">{t.notLinked}</span>
            )}
          </li>
        ))}
      </ul>
    </Card>
  );
}

function NewTask({ act }: { act: Act }) {
  const { m } = useI18n();
  const t = m.jarvisConsole.newTask;
  const [text, setText] = useState(m.jarvisConsole.sampleCommand);
  return (
    <Card className="p-5" data-testid="jarvis-new-task">
      <h2 className="mb-2 flex items-center gap-2 text-sm font-semibold text-ink">
        <Play className="h-4 w-4" aria-hidden /> {t.title}
      </h2>
      <textarea aria-label={t.textLabel} rows={3} className={INPUT} value={text} onChange={(e) => setText(e.target.value)} />
      <div className="mt-2 flex justify-end">
        <Button
          size="sm"
          disabled={text.trim().length < 5}
          onClick={() =>
            void act(() =>
              jarvisCall("/api/jarvis/tasks", { method: "POST", body: { text: text.trim(), idempotency_key: crypto.randomUUID() } }),
            )
          }
        >
          {t.start}
        </Button>
      </div>
    </Card>
  );
}

function Approval({ task, step, act }: { task: JarvisTask; step: JarvisStep; act: Act }) {
  const { m, f } = useI18n();
  const t = m.jarvisConsole.approval;
  const output = step.output as { recipient?: string; telegram_name?: string; documents?: { filename: string; sha256: string }[] };
  const recipient = `${output.recipient ?? ""}${output.telegram_name ? ` (${output.telegram_name})` : ""}`;
  const decide = (approve: boolean) =>
    act(() =>
      jarvisCall(`/api/jarvis/tasks/${task.id}/steps/${step.id}/decision`, {
        method: "POST",
        body: { scope_sha256: step.scope_sha256, approve },
      }),
    );
  return (
    <div className="mt-2 rounded-lg border border-amber-500/40 bg-amber-500/5 p-3 text-sm" data-testid="jarvis-approval">
      <p className="font-medium text-ink">
        <Send className="mr-1 inline h-3.5 w-3.5" aria-hidden />
        {f(t.question, { recipient })}
      </p>
      <ul className="my-1 list-disc pl-5 text-xs text-ink-muted">
        {(output.documents ?? []).map((d) => (
          <li key={d.sha256}>
            {d.filename} <span className="font-mono">{d.sha256.slice(0, 12)}…</span>
          </li>
        ))}
      </ul>
      <div className="flex gap-2">
        <Button size="sm" onClick={() => void decide(true)}>
          <Check className="mr-1 h-3.5 w-3.5" /> {t.approve}
        </Button>
        <Button size="sm" variant="secondary" onClick={() => void decide(false)}>
          <X className="mr-1 h-3.5 w-3.5" /> {t.reject}
        </Button>
      </div>
    </div>
  );
}

function Tasks({ tasks, act }: { tasks: JarvisTask[]; act: Act }) {
  const { m } = useI18n();
  const t = m.jarvisConsole.tasks;
  const steps = stepLabels(m.jarvisConsole);
  const states = stateLabels(m.jarvisConsole);
  if (tasks.length === 0) return null;
  return (
    <Card className="p-5" data-testid="jarvis-tasks">
      <h2 className="mb-3 text-sm font-semibold text-ink">{t.title}</h2>
      <ul className="space-y-4">
        {tasks.map((task) => (
          <li key={task.id} className="border-b border-line pb-3 last:border-0">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-sm text-ink">{task.request_text}</p>
              <span className="text-xs font-medium text-ink-muted">{states[task.state] ?? task.state}</span>
            </div>
            <ol className="mt-2 space-y-1 text-xs">
              {task.steps.map((step) => (
                <li key={step.id}>
                  <span className={cn(step.state === "completed" ? "text-emerald-600" : step.state === "failed" ? "text-red-600" : "text-ink-muted")}>
                    {step.position}. {steps[step.action] ?? step.action} — {states[step.state] ?? step.state}
                    {step.error_message ? `: ${step.error_message}` : ""}
                  </span>
                  {step.state === "awaiting_authorization" && step.scope_sha256 && <Approval task={task} step={step} act={act} />}
                </li>
              ))}
            </ol>
            {task.report && <pre className="mt-2 whitespace-pre-wrap text-xs text-ink">{task.report}</pre>}
            <div className="mt-2 flex gap-2">
              {["queued", "running", "awaiting_authorization"].includes(task.state) && (
                <Button size="sm" variant="secondary" onClick={() => void act(() => jarvisCall(`/api/jarvis/tasks/${task.id}/cancel`, { method: "POST" }))}>
                  {t.cancel}
                </Button>
              )}
              {task.state === "failed" && (
                <Button size="sm" variant="secondary" onClick={() => void act(() => jarvisCall(`/api/jarvis/tasks/${task.id}/retry`, { method: "POST" }))}>
                  <RotateCcw className="mr-1 h-3.5 w-3.5" /> {t.retry}
                </Button>
              )}
            </div>
          </li>
        ))}
      </ul>
    </Card>
  );
}
