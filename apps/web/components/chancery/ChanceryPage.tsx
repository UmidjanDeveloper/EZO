"use client";

import type { Appeal, GovMeeting, GovTask } from "@ezo/shared";
import { Button, Card, cn, SelectField, Spinner, TextAreaField, TextField } from "@ezo/ui";
import { CheckCircle2, ExternalLink, Plus } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n/context";
import { PageFrame } from "../pages/PageFrame";

type Tab = "appeals" | "tasks" | "meetings";
const CHANNELS = ["virtual_reception", "president_portal", "written", "oral", "phone", "other"] as const;

function StateBadge({ state }: { state: string }) {
  const { m } = useI18n();
  const t = m.chancery;
  const label: Record<string, string> = {
    overdue: t.overdue,
    due_soon: t.dueSoon,
    answered: t.answered,
    closed: t.closed,
    in_progress: t.inProgress,
    new: t.new,
    open: t.open,
    done: t.done,
    cancelled: t.cancelled,
  };
  const tone =
    state === "overdue"
      ? "bg-danger/10 text-danger"
      : state === "due_soon"
        ? "bg-warning/15 text-warning"
        : state === "answered" || state === "done" || state === "closed"
          ? "bg-success/15 text-success"
          : "bg-surface-2 text-ink-muted";
  return (
    <span className={cn("rounded-full px-2 py-0.5 text-[11px]", tone)} data-testid="chancery-state">
      {label[state] ?? state}
    </span>
  );
}

const day = (iso: string | null) => (iso ? iso.split("-").reverse().join(".") : "—");

/** Devonxona: the hokimiyat's appeals register, task register and meetings. */
export function ChanceryPage() {
  const { m } = useI18n();
  const t = m.chancery;
  const [tab, setTab] = useState<Tab>("appeals");
  const [appeals, setAppeals] = useState<Appeal[] | null>(null);
  const [tasks, setTasks] = useState<GovTask[] | null>(null);
  const [meetings, setMeetings] = useState<GovMeeting[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      const [a, tk, mt] = await Promise.all([api.appeals(), api.govTasks(), api.meetings()]);
      setAppeals(a);
      setTasks(tk);
      setMeetings(mt);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    void Promise.resolve().then(reload);
  }, [reload]);

  const tabs: [Tab, string, number | undefined][] = [
    ["appeals", t.appeals, appeals?.filter((a) => a.state === "overdue").length],
    ["tasks", t.tasks, tasks?.filter((x) => x.state === "overdue").length],
    ["meetings", t.meetings, undefined],
  ];

  return (
    <PageFrame title={t.title} subtitle={t.subtitle}>
      {error ? <p className="mb-4 text-sm text-danger">{error}</p> : null}
      <div className="mb-4 flex gap-1.5" role="tablist">
        {tabs.map(([key, label, late]) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={tab === key}
            onClick={() => setTab(key)}
            className={cn(
              "rounded-lg px-3 py-1.5 text-sm",
              tab === key ? "bg-accent text-white" : "bg-surface-2 text-ink-muted hover:text-ink",
            )}
            data-testid={`chancery-tab-${key}`}
          >
            {label}
            {late ? <span className="ml-1.5 rounded-full bg-danger px-1.5 text-[11px] text-white">{late}</span> : null}
          </button>
        ))}
      </div>
      {tab === "appeals" ? <Appeals rows={appeals} onChanged={() => void reload()} /> : null}
      {tab === "tasks" ? <Tasks rows={tasks} onChanged={() => void reload()} /> : null}
      {tab === "meetings" ? <Meetings rows={meetings} /> : null}
    </PageFrame>
  );
}

function Appeals({ rows, onChanged }: { rows: Appeal[] | null; onChanged: () => void }) {
  const { m } = useI18n();
  const t = m.chancery;
  const channelName = (c: string) => (t as Record<string, string>)[`channels_${c}`] ?? c;
  const [open, setOpen] = useState(false);
  const empty = { applicant: "", contact: "", channel: "virtual_reception", summary: "", assignee: "", due_on: "" };
  const [form, setForm] = useState(empty);
  const [error, setError] = useState<string | null>(null);
  if (rows === null) return <Spinner label={m.common.loading} />;
  return (
    <div className="flex flex-col gap-3">
      {open ? (
        <Card className="p-5">
          <form
            className="grid gap-3 sm:grid-cols-2"
            onSubmit={(e) => {
              e.preventDefault();
              setError(null);
              void api
                .createAppeal({ ...form, due_on: form.due_on || null })
                .then(() => {
                  setForm(empty);
                  setOpen(false);
                  onChanged();
                })
                .catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)));
            }}
          >
            <TextField label={t.applicant} value={form.applicant} onChange={(e) => setForm({ ...form, applicant: e.target.value })} required minLength={2} data-testid="appeal-applicant" />
            <TextField label={t.contact} value={form.contact} onChange={(e) => setForm({ ...form, contact: e.target.value })} />
            <SelectField label={t.channel} value={form.channel} onChange={(e) => setForm({ ...form, channel: e.target.value })}>
              {CHANNELS.map((c) => (
                <option key={c} value={c}>{channelName(c)}</option>
              ))}
            </SelectField>
            <TextField label={t.assignee} value={form.assignee} onChange={(e) => setForm({ ...form, assignee: e.target.value })} />
            <div className="sm:col-span-2">
              <TextAreaField label={t.summary} value={form.summary} onChange={(e) => setForm({ ...form, summary: e.target.value })} required minLength={3} rows={3} data-testid="appeal-summary" />
            </div>
            <TextField label={t.due} type="date" value={form.due_on} onChange={(e) => setForm({ ...form, due_on: e.target.value })} />
            {error ? <p className="text-sm text-danger sm:col-span-2">{error}</p> : null}
            <div className="flex gap-2 sm:col-span-2">
              <Button type="submit" data-testid="appeal-add">{t.add}</Button>
              <Button type="button" variant="ghost" onClick={() => setOpen(false)}>{m.common.cancel}</Button>
            </div>
          </form>
        </Card>
      ) : (
        <Button variant="secondary" className="self-start" onClick={() => setOpen(true)} data-testid="appeal-new">
          <Plus size={16} /> {t.newAppeal}
        </Button>
      )}
      {rows.length === 0 ? <p className="text-sm text-ink-muted">{t.emptyAppeals}</p> : null}
      {rows.map((a) => (
        <Card key={a.id} className="p-4 text-sm" data-testid="appeal-row">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-xs text-ink-faint">{a.number}</span>
            <span className="font-medium">{a.applicant}</span>
            <StateBadge state={a.state} />
            <span className="ml-auto text-xs text-ink-faint">
              {t.received}: {day(a.received_on)} · {t.due}: {day(a.due_on)}
            </span>
          </div>
          <p className="mt-1 text-ink-soft">{a.summary}</p>
          <p className="mt-1 text-xs text-ink-faint">
            {channelName(a.channel)}
            {a.contact ? ` · ${a.contact}` : ""} · {t.assignee}: {a.assignee || "—"}
            {a.assignee && !a.assignee_known ? <span className="text-warning"> ({t.unknownAssignee})</span> : null}
          </p>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            {a.status === "new" ? (
              <Button size="sm" variant="ghost" onClick={() => void api.updateAppeal(a.id, { status: "in_progress" }).then(onChanged)}>
                {t.markInProgress}
              </Button>
            ) : null}
            {a.status === "new" || a.status === "in_progress" ? (
              <Button size="sm" variant="secondary" onClick={() => void api.updateAppeal(a.id, { status: "answered" }).then(onChanged)} data-testid="appeal-answered">
                <CheckCircle2 size={14} /> {t.markAnswered}
              </Button>
            ) : null}
            {a.answer_artifact_id ? (
              <Link href={`/artifacts?open=${a.answer_artifact_id}`} className="inline-flex items-center gap-1 text-xs text-accent hover:underline">
                <ExternalLink size={12} /> {t.replyLetter}
              </Link>
            ) : a.status !== "answered" && a.status !== "closed" ? (
              <span className="text-xs text-ink-faint">{t.chatHint}</span>
            ) : null}
          </div>
        </Card>
      ))}
    </div>
  );
}

function Tasks({ rows, onChanged }: { rows: GovTask[] | null; onChanged: () => void }) {
  const { m } = useI18n();
  const t = m.chancery;
  const [form, setForm] = useState({ title: "", assignee: "", due_on: "" });
  if (rows === null) return <Spinner label={m.common.loading} />;
  return (
    <div className="flex flex-col gap-3">
      <Card className="p-4">
        <form
          className="grid items-end gap-2 sm:grid-cols-[2fr_1fr_1fr_auto]"
          onSubmit={(e) => {
            e.preventDefault();
            void api.createGovTask({ ...form, due_on: form.due_on || null }).then(() => {
              setForm({ title: "", assignee: "", due_on: "" });
              onChanged();
            });
          }}
        >
          <TextField label={t.newTask} value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} required minLength={3} data-testid="task-title" />
          <TextField label={t.assignee} value={form.assignee} onChange={(e) => setForm({ ...form, assignee: e.target.value })} />
          <TextField label={t.due} type="date" value={form.due_on} onChange={(e) => setForm({ ...form, due_on: e.target.value })} />
          <Button type="submit" data-testid="task-add">{t.add}</Button>
        </form>
      </Card>
      {rows.length === 0 ? <p className="text-sm text-ink-muted">{t.emptyTasks}</p> : null}
      {rows.map((task) => (
        <Card key={task.id} className="flex flex-wrap items-center gap-2 p-3 text-sm" data-testid="task-row">
          <span className="font-mono text-xs text-ink-faint">{task.number}</span>
          <span className={cn("flex-1", task.status !== "open" && "text-ink-faint line-through")}>{task.title}</span>
          <span className="text-xs text-ink-muted">
            {task.assignee || "—"}
            {task.assignee && !task.assignee_known ? <span className="text-warning"> *</span> : null} · {day(task.due_on)}
          </span>
          <StateBadge state={task.state} />
          {task.status === "open" ? (
            <Button size="sm" variant="secondary" onClick={() => void api.updateGovTask(task.id, { status: "done" }).then(onChanged)} data-testid="task-done">
              {t.markDone}
            </Button>
          ) : null}
        </Card>
      ))}
    </div>
  );
}

function Meetings({ rows }: { rows: GovMeeting[] | null }) {
  const { m } = useI18n();
  const t = m.chancery;
  if (rows === null) return <Spinner label={m.common.loading} />;
  return (
    <div className="flex flex-col gap-2">
      {rows.length === 0 ? <p className="text-sm text-ink-muted">{t.emptyMeetings}</p> : null}
      {rows.map((meeting) => (
        <Card key={meeting.id} className="flex items-center gap-3 p-3 text-sm">
          <span className="text-xs text-ink-faint">{day(meeting.held_on)}</span>
          <span className="flex-1 font-medium">{meeting.title}</span>
          {meeting.minutes_artifact_id ? (
            <Link href={`/artifacts?open=${meeting.minutes_artifact_id}`} className="inline-flex items-center gap-1 text-xs text-accent hover:underline">
              <ExternalLink size={12} /> {t.minutes}
            </Link>
          ) : null}
        </Card>
      ))}
    </div>
  );
}
