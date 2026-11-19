"use client";

import type { ScheduledJobInfo, ScheduledRunInfo, ScheduleKind } from "@ezo/shared";
import { Button, Card, cn, SelectField, Spinner, TextField } from "@ezo/ui";
import { Pause, Play, Plus, RotateCw, Trash2 } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n/context";
import { jarvisCall, type JarvisRecipient } from "@/lib/jarvis-api";
import { PageFrame } from "../pages/PageFrame";

const KINDS: ScheduleKind[] = ["weekly_report", "monthly_report", "deadline_digest", "district_sync", "lexuz_recheck"];

const stamp = (iso: string | null) => (iso ? new Date(iso).toLocaleString(undefined, { dateStyle: "short", timeStyle: "short" }) : "—");

/** Jadval: EZO's recurring jobs and their results. */
export function SchedulePage() {
  const { m } = useI18n();
  const t = m.schedule;
  const [jobs, setJobs] = useState<ScheduledJobInfo[] | null>(null);
  const [runs, setRuns] = useState<ScheduledRunInfo[]>([]);
  const [recipients, setRecipients] = useState<JarvisRecipient[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [form, setForm] = useState({ kind: "weekly_report" as ScheduleKind, days: [1] as number[], time: "09:00", monthDay: "1", recipient: "" });

  const reload = useCallback(async () => {
    try {
      const data = await api.schedule();
      setJobs(data.jobs);
      setRuns(data.runs);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    void Promise.resolve().then(reload);
    void jarvisCall<JarvisRecipient[]>("/api/jarvis/telegram/recipients")
      .then((rows) => setRecipients(rows.filter((r) => r.status === "verified")))
      .catch(() => undefined);
  }, [reload]);

  const act = (key: string, work: () => Promise<unknown>) => {
    setBusy(key);
    setError(null);
    void work()
      .then(() => reload())
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setBusy(null));
  };

  const monthly = form.kind === "monthly_report";

  return (
    <PageFrame title={t.title} subtitle={t.subtitle}>
      {error ? <p className="mb-4 text-sm text-danger">{error}</p> : null}
      <Card className="mb-4 p-4">
        <form
          className="grid gap-3 sm:grid-cols-2"
          onSubmit={(e) => {
            e.preventDefault();
            act("add", () =>
              api.createScheduledJob({
                kind: form.kind,
                weekdays: monthly ? "" : form.days.join(","),
                at_time: form.time,
                month_day: monthly ? Number(form.monthDay) : null,
                notify_recipient_id: form.recipient || null,
              }),
            );
          }}
        >
          <SelectField label={t.kind} value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value as ScheduleKind })} data-testid="schedule-kind">
            {KINDS.map((k) => (
              <option key={k} value={k}>
                {t.kinds[k]}
              </option>
            ))}
          </SelectField>
          <TextField label={t.time} type="time" value={form.time} onChange={(e) => setForm({ ...form, time: e.target.value })} required />
          {monthly ? (
            <TextField label={t.monthDay} type="number" min={1} max={31} value={form.monthDay} onChange={(e) => setForm({ ...form, monthDay: e.target.value })} />
          ) : (
            <div>
              <p className="mb-1 text-sm text-ink-muted">{t.days}</p>
              <div className="flex flex-wrap gap-1">
                {t.weekdays.map((label, i) => {
                  const day = i + 1;
                  const on = form.days.includes(day);
                  return (
                    <button
                      key={label}
                      type="button"
                      onClick={() => setForm({ ...form, days: on ? form.days.filter((d) => d !== day) : [...form.days, day].sort() })}
                      className={cn("rounded-md px-2 py-1 text-xs", on ? "bg-accent text-white" : "bg-surface-2 text-ink-muted")}
                    >
                      {label}
                    </button>
                  );
                })}
                <span className="ml-1 self-center text-xs text-ink-faint">{form.days.length === 0 ? t.everyDay : ""}</span>
              </div>
            </div>
          )}
          <SelectField label={t.telegram} value={form.recipient} onChange={(e) => setForm({ ...form, recipient: e.target.value })}>
            <option value="">{t.noTelegram}</option>
            {recipients.map((r) => (
              <option key={r.id} value={r.id}>
                {r.label}
                {r.telegram_name ? ` (${r.telegram_name})` : ""}
              </option>
            ))}
          </SelectField>
          <div className="sm:col-span-2">
            <Button type="submit" disabled={busy === "add"} data-testid="schedule-add">
              <Plus size={16} /> {t.add}
            </Button>
          </div>
        </form>
      </Card>
      {jobs === null ? <Spinner label={m.common.loading} /> : null}
      {jobs?.length === 0 ? <p className="text-sm text-ink-muted">{t.empty}</p> : null}
      <div className="flex flex-col gap-3">
        {jobs?.map((job) => {
          const mine = runs.filter((r) => r.job_id === job.id).slice(0, 3);
          return (
            <Card key={job.id} className="p-4 text-sm" data-testid="schedule-row">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium">{t.kinds[job.kind] ?? job.title}</span>
                <span className="text-ink-muted">· {job.when}</span>
                {job.enabled ? (
                  <span className="text-xs text-ink-faint">
                    {t.next}: {stamp(job.next_run_at)}
                  </span>
                ) : (
                  <span className="rounded-full bg-surface-2 px-2 py-0.5 text-[11px] text-ink-muted">{t.stopped}</span>
                )}
                <div className="ml-auto flex gap-1">
                  <Button variant="ghost" disabled={busy !== null} onClick={() => act(`run-${job.id}`, () => api.runScheduledJob(job.id))} title={t.runNow} data-testid="schedule-run">
                    <RotateCw size={15} />
                  </Button>
                  <Button variant="ghost" disabled={busy !== null} onClick={() => act(`toggle-${job.id}`, () => api.updateScheduledJob(job.id, { enabled: !job.enabled }))} title={job.enabled ? t.pause : t.resume}>
                    {job.enabled ? <Pause size={15} /> : <Play size={15} />}
                  </Button>
                  <Button
                    variant="ghost"
                    disabled={busy !== null}
                    onClick={() => {
                      if (window.confirm(t.remove + "?")) act(`del-${job.id}`, () => api.deleteScheduledJob(job.id));
                    }}
                    title={t.remove}
                  >
                    <Trash2 size={15} />
                  </Button>
                </div>
              </div>
              <div className="mt-2 flex flex-col gap-1">
                {mine.length === 0 ? <p className="text-xs text-ink-faint">{t.noRuns}</p> : null}
                {mine.map((run) => (
                  <div key={run.id} className="rounded-lg bg-surface-2 p-2 text-xs" data-testid="schedule-run-result">
                    <p className={cn("mb-1", run.status === "failed" ? "text-danger" : "text-ink-muted")}>
                      {stamp(run.started_at)} · {run.status}
                      {run.notified ? ` · ${t.sentTelegram}` : ""}
                    </p>
                    <p className="whitespace-pre-wrap text-ink-soft">{run.error ?? run.summary}</p>
                    {run.artifact_id ? (
                      <Link className="mt-1 inline-block text-accent underline" href={`/artifacts?open=${run.artifact_id}`}>
                        {t.openFile}
                      </Link>
                    ) : null}
                  </div>
                ))}
              </div>
            </Card>
          );
        })}
      </div>
    </PageFrame>
  );
}
