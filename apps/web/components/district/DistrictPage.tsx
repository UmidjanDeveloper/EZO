"use client";

import type {
  DistrictChannels,
  DistrictMember,
  DistrictNotice,
  DistrictPerson,
  DistrictProject,
  DistrictSource,
  DistrictSummary,
} from "@ezo/shared";
import { Button, Card, cn, SelectField, Spinner, TextField } from "@ezo/ui";
import { AlertTriangle, CheckCircle2, Plus, RefreshCw, Trash2, Upload } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { jarvisCall } from "@/lib/jarvis-api";
import { useI18n } from "@/lib/i18n/context";
import { PageFrame } from "../pages/PageFrame";
import { NoticeCard } from "./NoticeCard";

interface Detail {
  project: DistrictProject;
  summary: DistrictSummary;
  people: DistrictPerson[];
}

interface Recipient {
  id: string;
  label: string;
  status: string;
}

function Progress({ percent, expected }: { percent: number | null; expected: number | null }) {
  return (
    <div className="relative h-2 w-full overflow-hidden rounded-full bg-surface-2" aria-hidden>
      <div className="h-full rounded-full bg-accent" style={{ width: `${Math.min(100, percent ?? 0)}%` }} />
      {expected !== null ? (
        <div className="absolute top-0 h-full w-0.5 bg-ink/60" style={{ left: `${Math.min(100, expected * 100)}%` }} />
      ) : null}
    </div>
  );
}

/**
 * District center: projects, who is behind, warnings. Every number shown comes from the API
 * (official source, imported table or manual entry); warnings leave EZO only after "Send".
 */
export function DistrictPage() {
  const { m, f } = useI18n();
  const t = m.district;
  const [channels, setChannels] = useState<DistrictChannels | null>(null);
  const [projects, setProjects] = useState<DistrictProject[] | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [notices, setNotices] = useState<DistrictNotice[]>([]);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      const [c, p, n] = await Promise.all([api.districtChannels(), api.districtProjects(), api.districtNotices()]);
      setChannels(c);
      setProjects(p);
      setNotices(n);
      setSelected((current) => current ?? p[0]?.id ?? null);
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
      {channels ? <Channels channels={channels} /> : null}
      <NewProject onCreated={(id) => { setSelected(id); void reload(); }} />
      {projects === null ? (
        <Spinner label={m.common.loading} />
      ) : projects.length === 0 ? (
        <p className="mt-6 text-sm text-ink-muted" data-testid="district-empty">{t.empty}</p>
      ) : (
        <div className="mt-6 flex flex-col gap-4">
          <div className="grid gap-3 sm:grid-cols-2" data-testid="district-projects">
            {projects.map((p) => (
              <button
                key={p.id}
                type="button"
                onClick={() => setSelected(p.id)}
                className={cn(
                  "rounded-xl border p-4 text-left transition-colors",
                  selected === p.id ? "border-accent bg-accent/5" : "border-line hover:bg-surface-2",
                )}
                data-testid="district-project"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium">{p.name}</span>
                  <span className="text-sm tabular-nums">{p.summary?.percent ?? 0}%</span>
                </div>
                <div className="mt-2">
                  <Progress percent={p.summary?.percent ?? null} expected={p.summary?.expected_share ?? null} />
                </div>
                <div className="mt-2 flex flex-wrap gap-3 text-xs text-ink-faint">
                  <span>
                    {p.summary?.done ?? 0} / {p.summary?.target ?? 0} {p.unit}
                  </span>
                  {p.summary?.behind ? <span className="text-danger">{f(t.behindCount, { n: p.summary.behind })}</span> : null}
                  {p.summary?.days_left !== null && p.summary?.days_left !== undefined ? (
                    <span>{f(t.daysLeft, { n: p.summary.days_left })}</span>
                  ) : null}
                </div>
              </button>
            ))}
          </div>
          {selected ? (
            <ProjectDetail
              key={selected}
              id={selected}
              canSend={channels?.can_send ?? false}
              onChanged={() => void reload()}
              onDeleted={() => { setSelected(null); void reload(); }}
            />
          ) : null}
        </div>
      )}
      <Card className="mt-6 p-5" data-testid="district-notices">
        <h2 className="text-lg font-semibold">{t.notices}</h2>
        {notices.length === 0 ? <p className="mt-2 text-sm text-ink-muted">{t.noNotices}</p> : null}
        {notices.map((n) => (
          <NoticeCard key={`${n.id}-${n.status}`} notice={n} canSend={channels?.can_send ?? false} onChanged={() => void reload()} />
        ))}
      </Card>
    </PageFrame>
  );
}

function Channels({ channels }: { channels: DistrictChannels }) {
  const { m, f } = useI18n();
  const t = m.district;
  const line = (ok: boolean, text: string) => (
    <li className={cn("flex items-center gap-1.5", ok ? "text-ink" : "text-ink-faint")}>
      {ok ? <CheckCircle2 size={14} className="text-success" /> : <AlertTriangle size={14} />} {text}
    </li>
  );
  return (
    <Card className="mb-4 p-4 text-sm" data-testid="district-channels">
      <p className="font-medium">{t.channels}</p>
      <ul className="mt-1 flex flex-col gap-0.5">
        {line(channels.telegram, channels.telegram ? t.telegramOn : t.telegramOff)}
        {line(channels.sms, channels.sms ? f(t.smsOn, { sender: channels.sms_sender ?? "" }) : t.smsOff)}
      </ul>
      {!channels.can_send ? <p className="mt-2 text-xs text-ink-faint">{t.ownerOnly}</p> : null}
    </Card>
  );
}

function NewProject({ onCreated }: { onCreated: (id: string) => void }) {
  const { m } = useI18n();
  const t = m.district;
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ name: "", unit: "", responsible_org: "", start_date: "", deadline: "" });
  const [error, setError] = useState<string | null>(null);
  const set = (key: keyof typeof form) => (e: { target: { value: string } }) => setForm({ ...form, [key]: e.target.value });

  if (!open) {
    return (
      <Button variant="secondary" onClick={() => setOpen(true)} data-testid="district-new">
        <Plus size={16} /> {t.newProject}
      </Button>
    );
  }
  return (
    <Card className="p-5">
      <form
        className="grid gap-3 sm:grid-cols-2"
        onSubmit={(e) => {
          e.preventDefault();
          setError(null);
          void api
            .createDistrictProject({
              name: form.name.trim(),
              unit: form.unit.trim() || t.unitPlaceholder,
              responsible_org: form.responsible_org.trim(),
              start_date: form.start_date || null,
              deadline: form.deadline || null,
            })
            .then((p) => {
              setOpen(false);
              setForm({ name: "", unit: "", responsible_org: "", start_date: "", deadline: "" });
              onCreated(p.id);
            })
            .catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)));
        }}
      >
        <TextField label={t.name} placeholder={t.namePlaceholder} value={form.name} onChange={set("name")} required minLength={2} data-testid="district-name" />
        <TextField label={t.unit} placeholder={t.unitPlaceholder} value={form.unit} onChange={set("unit")} />
        <TextField label={t.org} placeholder={t.orgPlaceholder} value={form.responsible_org} onChange={set("responsible_org")} />
        <div className="grid grid-cols-2 gap-3">
          <TextField label={t.start} type="date" value={form.start_date} onChange={set("start_date")} />
          <TextField label={t.deadline} type="date" value={form.deadline} onChange={set("deadline")} />
        </div>
        {error ? <p className="text-sm text-danger sm:col-span-2">{error}</p> : null}
        <div className="flex gap-2 sm:col-span-2">
          <Button type="submit" data-testid="district-create">{t.create}</Button>
          <Button type="button" variant="ghost" onClick={() => setOpen(false)}>{m.common.cancel}</Button>
        </div>
      </form>
    </Card>
  );
}

function ProjectDetail({
  id,
  canSend,
  onChanged,
  onDeleted,
}: {
  id: string;
  canSend: boolean;
  onChanged: () => void;
  onDeleted: () => void;
}) {
  const { m, f } = useI18n();
  const t = m.district;
  const [detail, setDetail] = useState<Detail | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<DistrictNotice[]>([]);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    void api.districtProject(id).then(setDetail).catch((e: unknown) => setMessage(String(e)));
  }, [id]);
  useEffect(load, [load]);

  if (!detail) return <Spinner label={m.common.loading} />;
  const { project, summary, people } = detail;

  async function run(action: () => Promise<string>) {
    setBusy(true);
    try {
      setMessage(await action());
      load();
      onChanged();
    } catch (e) {
      setMessage(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="p-5" data-testid="district-detail">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">{project.name}</h2>
          {project.responsible_org ? <p className="text-sm text-ink-muted">{project.responsible_org}</p> : null}
          <p className="mt-1 text-sm tabular-nums" data-testid="district-summary">
            {t.done}: {summary.done} / {summary.target} {project.unit} ({summary.percent ?? 0}%)
            {summary.expected_share !== null ? ` · ${f(t.expected, { p: Math.round(summary.expected_share * 100) })}` : ""}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <label className={cn("inline-flex cursor-pointer items-center gap-1.5 rounded-lg border border-line px-3 py-1.5 text-sm hover:bg-surface-2", busy && "opacity-50")} title={t.importHint}>
            <Upload size={14} /> {t.importTable}
            <input
              type="file"
              accept=".xlsx,.csv"
              className="hidden"
              data-testid="district-import"
              onChange={(e) => {
                const file = e.target.files?.[0];
                e.target.value = "";
                if (!file) return;
                void run(async () => {
                  const r = await api.importDistrictTable(id, file, file.name);
                  return f(t.imported, { rows: r.rows, updated: r.updated, created: r.created_people });
                });
              }}
            />
          </label>
          {project.source_kind === "api" ? (
            <Button
              size="sm"
              variant="secondary"
              disabled={busy}
              onClick={() =>
                void run(async () => {
                  const r = await api.syncDistrictProject(id);
                  return r.ok ? f(t.synced, { updated: r.updated }) : f(t.syncFailed, { error: r.error ?? "" });
                })
              }
            >
              <RefreshCw size={14} /> {t.sync}
            </Button>
          ) : null}
          <Button
            size="sm"
            variant="ghost"
            className="text-danger"
            onClick={() => {
              if (!window.confirm(f(t.confirmDelete, { name: project.name }))) return;
              void api.deleteDistrictProject(id).then(onDeleted);
            }}
          >
            <Trash2 size={14} /> {t.delete}
          </Button>
        </div>
      </div>
      {project.last_sync_error ? (
        <p className="mt-2 text-sm text-danger">{f(t.syncFailed, { error: project.last_sync_error })}</p>
      ) : project.last_sync_at ? (
        <p className="mt-2 text-xs text-ink-faint">{f(t.lastSync, { at: new Date(project.last_sync_at).toLocaleString() })}</p>
      ) : null}
      {message ? <p className="mt-2 text-sm" data-testid="district-message">{message}</p> : null}

      {people.length ? (
        <div className="mt-4 overflow-x-auto">
          <table className="w-full text-sm" data-testid="district-people">
            <thead className="text-left text-xs text-ink-faint">
              <tr>
                <th className="py-1 pr-2">{t.person}</th>
                <th className="py-1 pr-2">{t.area}</th>
                <th className="py-1 pr-2 text-right">{t.plan}</th>
                <th className="py-1 pr-2 text-right">{t.done}</th>
                <th className="py-1 pr-2 text-right">{t.percent}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {people.map((p) => (
                <tr key={p.member_id} className="border-t border-line" data-testid="district-person">
                  <td className="py-1.5 pr-2">
                    {p.name}
                    {p.behind ? <span className="ml-2 rounded bg-danger/10 px-1.5 py-0.5 text-[11px] text-danger">{t.behind}</span> : null}
                  </td>
                  <td className="py-1.5 pr-2 text-ink-muted">{p.area}</td>
                  <td className="py-1.5 pr-2 text-right tabular-nums">{p.target}</td>
                  <td className="py-1.5 pr-2 text-right tabular-nums">{p.done}</td>
                  <td className="py-1.5 pr-2 text-right tabular-nums">{p.percent ?? "—"}%</td>
                  <td className="py-1.5 text-right">
                    <Button
                      size="sm"
                      variant="ghost"
                      data-testid="district-warn"
                      onClick={() =>
                        void api.draftDistrictNotice(id, p.member_id).then((n) => {
                          setDrafts((d) => [n, ...d]);
                          onChanged();
                        })
                      }
                    >
                      {t.warn}
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="mt-4 text-sm text-ink-muted">{t.importHint}</p>
      )}
      {drafts.map((n) => (
        <NoticeCard key={n.id} notice={n} canSend={canSend} onChanged={onChanged} />
      ))}
      <SourceForm project={project} onSaved={(text) => { setMessage(text); load(); onChanged(); }} />
      <Contacts onSaved={() => onChanged()} />
    </Card>
  );
}

const FIELDS = ["name", "target", "done", "phone", "area", "external_id"] as const;

function SourceForm({ project, onSaved }: { project: DistrictProject; onSaved: (text: string) => void }) {
  const { m } = useI18n();
  const t = m.district;
  const [kind, setKind] = useState(project.source_kind);
  const [source, setSource] = useState<DistrictSource>({
    token_env: "EZO_DISTRICT_API_TOKEN",
    items_path: "",
    ...project.source,
    fields: { ...(project.source.fields ?? {}) },
  });
  const labels: Record<(typeof FIELDS)[number], string> = {
    name: t.fieldName,
    target: t.fieldTarget,
    done: t.fieldDone,
    phone: t.fieldPhone,
    area: t.fieldArea,
    external_id: t.fieldId,
  };
  return (
    <details className="mt-5 rounded-xl border border-line p-4" data-testid="district-source">
      <summary className="cursor-pointer text-sm font-medium">{t.source}: {kind === "api" ? t.sourceApi : kind === "import" ? t.sourceImport : t.sourceManual}</summary>
      <form
        className="mt-3 grid gap-3 sm:grid-cols-2"
        onSubmit={(e) => {
          e.preventDefault();
          void api
            .updateDistrictProject(project.id, { source_kind: kind, source })
            .then(() => onSaved(t.save + " ✓"))
            .catch((err: unknown) => onSaved(err instanceof Error ? err.message : String(err)));
        }}
      >
        <SelectField label={t.source} value={kind} onChange={(e) => setKind(e.target.value as DistrictProject["source_kind"])}>
          <option value="manual">{t.sourceManual}</option>
          <option value="import">{t.sourceImport}</option>
          <option value="api">{t.sourceApi}</option>
        </SelectField>
        {kind === "api" ? (
          <>
            <TextField label={t.apiUrl} value={source.url ?? ""} onChange={(e) => setSource({ ...source, url: e.target.value })} placeholder="https://" />
            <TextField label={t.tokenEnv} hint={t.tokenNote} value={source.token_env ?? ""} onChange={(e) => setSource({ ...source, token_env: e.target.value })} />
            <TextField label={t.itemsPath} value={source.items_path ?? ""} onChange={(e) => setSource({ ...source, items_path: e.target.value })} placeholder="data.items" />
            {FIELDS.map((key) => (
              <TextField
                key={key}
                label={labels[key]}
                value={source.fields?.[key] ?? ""}
                onChange={(e) => setSource({ ...source, fields: { ...source.fields, [key]: e.target.value } })}
              />
            ))}
          </>
        ) : null}
        <div className="sm:col-span-2">
          <Button type="submit" size="sm">{t.saveSource}</Button>
        </div>
      </form>
    </details>
  );
}

function Contacts({ onSaved }: { onSaved: () => void }) {
  const { m } = useI18n();
  const t = m.district;
  const [members, setMembers] = useState<DistrictMember[]>([]);
  const [recipients, setRecipients] = useState<Recipient[]>([]);
  const [edits, setEdits] = useState<Record<string, Partial<DistrictMember>>>({});

  useEffect(() => {
    void api.districtMembers().then(setMembers).catch(() => setMembers([]));
    void jarvisCall<Recipient[]>("/api/jarvis/telegram/recipients")
      .then((rows) => setRecipients(rows.filter((r) => r.status === "verified")))
      .catch(() => setRecipients([]));
  }, []);

  if (!members.length) return null;
  return (
    <details className="mt-3 rounded-xl border border-line p-4" data-testid="district-contacts">
      <summary className="cursor-pointer text-sm font-medium">{t.contacts}</summary>
      <p className="mt-2 text-xs text-ink-faint">{t.linkHint}</p>
      <div className="mt-2 flex flex-col gap-2">
        {members.map((member) => {
          const edit = { ...member, ...edits[member.id] };
          return (
            <div key={member.id} className="grid items-end gap-2 sm:grid-cols-[1fr_1fr_1fr_auto]">
              <span className="text-sm">{member.full_name}</span>
              <TextField label={t.phone} value={edit.phone ?? ""} onChange={(e) => setEdits({ ...edits, [member.id]: { ...edits[member.id], phone: e.target.value } })} placeholder="+998 90 123 45 67" />
              <SelectField
                label={t.telegram}
                value={edit.telegram_recipient_id ?? ""}
                onChange={(e) => setEdits({ ...edits, [member.id]: { ...edits[member.id], telegram_recipient_id: e.target.value || null } })}
              >
                <option value="">{t.noTelegram}</option>
                {recipients.map((r) => (
                  <option key={r.id} value={r.id}>{r.label}</option>
                ))}
              </SelectField>
              <Button
                size="sm"
                variant="secondary"
                disabled={!edits[member.id]}
                onClick={() => {
                  const body = {
                    full_name: edit.full_name,
                    position: edit.position,
                    area: edit.area,
                    phone: edit.phone || null,
                    external_id: edit.external_id,
                    telegram_recipient_id: edit.telegram_recipient_id,
                  };
                  void api.updateDistrictMember(member.id, body).then((saved) => {
                    setMembers((all) => all.map((x) => (x.id === saved.id ? saved : x)));
                    setEdits((all) => Object.fromEntries(Object.entries(all).filter(([key]) => key !== member.id)));
                    onSaved();
                  });
                }}
              >
                {t.save}
              </Button>
            </div>
          );
        })}
      </div>
    </details>
  );
}
