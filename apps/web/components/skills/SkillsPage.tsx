"use client";

import type { SkillDetail, SkillSummary } from "@ezo/shared";
import { Button, Card, cn, Spinner } from "@ezo/ui";
import { AlertTriangle, CheckCircle2, ShieldCheck } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n/context";
import { PageFrame } from "../pages/PageFrame";

/** Ko'nikmalar: review the code EZO wrote for itself and approve exactly that code. */
export function SkillsPage() {
  const { m } = useI18n();
  const t = m.skills;
  const [rows, setRows] = useState<SkillSummary[] | null>(null);
  const [worker, setWorker] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      const data = await api.skills();
      setRows(data.skills);
      setWorker(data.worker);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    void Promise.resolve().then(reload);
  }, [reload]);

  return (
    <PageFrame title={t.title} subtitle={t.subtitle}>
      {error ? <p className="mb-4 text-sm text-danger">{error}</p> : null}
      {!worker ? (
        <p className="mb-4 rounded-lg bg-warning/15 px-3 py-2 text-sm text-warning" data-testid="skills-worker-off">
          {t.workerOff}
        </p>
      ) : null}
      {rows === null ? <Spinner label={m.common.loading} /> : null}
      {rows?.length === 0 ? <p className="text-sm text-ink-muted">{t.empty}</p> : null}
      <div className="flex flex-col gap-3">
        {rows?.map((s) => (
          <Card key={s.id} className="p-4 text-sm" data-testid="skill-row">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium">{s.name}</span>
              <StatusBadge skill={s} />
              <Button
                variant="ghost"
                className="ml-auto"
                onClick={() => setOpenId(openId === s.id ? null : s.id)}
                data-testid="skill-open"
              >
                {t.open}
              </Button>
            </div>
            {s.description ? <p className="mt-1 text-ink-soft">{s.description}</p> : null}
            {openId === s.id ? <SkillReview id={s.id} onChanged={() => void reload()} /> : null}
          </Card>
        ))}
      </div>
    </PageFrame>
  );
}

function StatusBadge({ skill }: { skill: SkillSummary }) {
  const { m } = useI18n();
  const t = m.skills;
  const label = skill.approved ? t.approved : skill.status === "disabled" ? t.disabled : t.draft;
  return (
    <span
      className={cn(
        "rounded-full px-2 py-0.5 text-[11px]",
        skill.approved ? "bg-success/15 text-success" : "bg-surface-2 text-ink-muted",
      )}
      data-testid="skill-status"
    >
      {label}
    </span>
  );
}

function SkillReview({ id, onChanged }: { id: string; onChanged: () => void }) {
  const { m } = useI18n();
  const t = m.skills;
  const [skill, setSkill] = useState<SkillDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setSkill(await api.skill(id));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [id]);

  useEffect(() => {
    void Promise.resolve().then(load);
  }, [load]);

  const act = (work: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    void work()
      .then(() => load())
      .then(onChanged)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setBusy(false));
  };

  if (skill === null) return error ? <p className="mt-3 text-danger">{error}</p> : <Spinner label={m.common.loading} />;
  const ok = Boolean(skill.checks.ok);
  return (
    <div className="mt-3 flex flex-col gap-3" data-testid="skill-review">
      <p className={cn("flex items-center gap-1.5", ok ? "text-success" : "text-danger")}>
        {ok ? <CheckCircle2 size={16} /> : <AlertTriangle size={16} />}
        {ok ? t.checksOk : t.checksFailed}
      </p>
      {skill.checks.problems?.length ? (
        <ul className="list-disc pl-5 text-danger">
          {skill.checks.problems.map((p) => (
            <li key={p}>{p}</li>
          ))}
        </ul>
      ) : null}
      {skill.input_hint ? (
        <p>
          <span className="text-ink-muted">{t.input}: </span>
          {skill.input_hint}
        </p>
      ) : null}
      <div>
        <p className="mb-1 text-ink-muted">{t.code}</p>
        <pre className="max-h-96 overflow-auto rounded-lg bg-surface-2 p-3 text-xs" data-testid="skill-code">
          {skill.code}
        </pre>
        <p className="mt-1 break-all font-mono text-[11px] text-ink-faint">
          {t.hash}: {skill.code_sha256}
        </p>
      </div>
      {error ? <p className="text-danger">{error}</p> : null}
      <div className="flex flex-wrap gap-2">
        {!skill.approved && ok ? (
          <Button
            disabled={busy}
            onClick={() => {
              if (window.confirm(t.approveConfirm)) act(() => api.approveSkill(skill.id, skill.code_sha256));
            }}
            data-testid="skill-approve"
          >
            <ShieldCheck size={16} /> {t.approve}
          </Button>
        ) : null}
        {skill.approved ? (
          <Button variant="secondary" disabled={busy} onClick={() => act(() => api.disableSkill(skill.id))}>
            {t.disable}
          </Button>
        ) : null}
        <Button
          variant="ghost"
          disabled={busy}
          onClick={() => {
            if (window.confirm(t.remove + "?")) act(() => api.deleteSkill(skill.id));
          }}
        >
          {t.remove}
        </Button>
      </div>
      <div>
        <p className="mb-1 text-ink-muted">{t.runs}</p>
        {skill.runs.length === 0 ? <p className="text-ink-faint">{t.noRuns}</p> : null}
        {skill.runs.map((r) => (
          <p key={r.id} className="font-mono text-[11px] text-ink-soft">
            {r.created_at?.slice(0, 16).replace("T", " ")} · {r.status}
            {r.duration_ms != null ? ` · ${r.duration_ms} ms` : ""} ·{" "}
            {r.error ?? JSON.stringify(r.output)?.slice(0, 200)}
          </p>
        ))}
      </div>
    </div>
  );
}
