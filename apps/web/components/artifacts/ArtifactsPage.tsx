"use client";

import type { Artifact, ArtifactDetail, ArtifactType, ArtifactVersion } from "@ezo/shared";
import { ApiError } from "@ezo/shared";
import { Badge, Button, Card, cn, Spinner } from "@ezo/ui";
import { ChevronDown, Download, History, Pencil, Save, Trash2, Type } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { useApp } from "@/lib/app-state";
import { api } from "@/lib/api";
import { formatBytes, saveBlob } from "@/lib/download";
import { useI18n } from "@/lib/i18n/context";
import { useApiData } from "@/lib/use-api-data";
import { PageFrame } from "../pages/PageFrame";
import { ArtifactIcon } from "./ArtifactIcon";
import { VersionExports } from "./VersionExports";

const STATUS_TONE = { draft: "neutral", generating: "accent", ready: "success", failed: "danger" } as const;

export function ArtifactsPage() {
  const { m } = useI18n();
  const params = useSearchParams();
  const fetchArtifacts = useCallback(() => api.listArtifacts(), []);
  const { data: artifacts, error, reload } = useApiData(fetchArtifacts);
  const fetchProjects = useCallback(() => api.listProjects(), []);
  const { data: projects } = useApiData(fetchProjects);
  const [filter, setFilter] = useState<ArtifactType | "all">("all");
  const [openId, setOpenId] = useState<string | null>(() => params.get("open"));

  const projectNames = useMemo(() => new Map((projects ?? []).map((p) => [p.id, p.name])), [projects]);
  const types = useMemo(() => [...new Set((artifacts ?? []).map((a) => a.type))], [artifacts]);
  const visible = (artifacts ?? []).filter((a) => filter === "all" || a.type === filter);

  return (
    <PageFrame title={m.artifacts.title} subtitle={m.artifacts.subtitle}>
      {types.length > 1 ? (
        <div className="mb-4 flex flex-wrap gap-1.5" role="group" data-testid="artifact-filters">
          {(["all", ...types] as const).map((type) => (
            <button
              key={type}
              type="button"
              onClick={() => setFilter(type)}
              aria-pressed={filter === type}
              className={cn(
                "rounded-full border px-3 py-1 text-xs transition-colors",
                filter === type ? "border-accent/50 bg-accent/10 text-accent" : "border-line text-ink-muted hover:text-ink",
              )}
            >
              {type === "all" ? m.artifacts.all : m.artifacts.types[type]}
            </button>
          ))}
        </div>
      ) : null}

      <div className="flex flex-col gap-2" data-testid="artifact-list">
        {error ? (
          <p className="text-sm text-danger">{error.message}</p>
        ) : !artifacts ? (
          <Spinner label={m.common.loading} />
        ) : visible.length === 0 ? (
          <p className="py-8 text-center text-sm text-ink-muted">{m.artifacts.empty}</p>
        ) : (
          visible.map((artifact) => (
            <ArtifactRow
              key={artifact.id}
              artifact={artifact}
              projectName={artifact.project_id ? projectNames.get(artifact.project_id) : undefined}
              open={openId === artifact.id}
              onToggle={() => setOpenId(openId === artifact.id ? null : artifact.id)}
              onChanged={reload}
            />
          ))
        )}
      </div>
    </PageFrame>
  );
}

function ArtifactRow({
  artifact,
  projectName,
  open,
  onToggle,
  onChanged,
}: {
  artifact: Artifact;
  projectName?: string;
  open: boolean;
  onToggle: () => void;
  onChanged: () => void;
}) {
  const { m, f } = useI18n();
  const details = [
    m.artifacts.types[artifact.type],
    projectName ?? m.artifacts.noProject,
    new Date(artifact.updated_at).toLocaleDateString(),
    artifact.current_version ? f(m.artifacts.version, { n: artifact.current_version.version_number }) : null,
  ].filter(Boolean);

  return (
    <Card className="px-4 py-3" data-testid="artifact-row" data-artifact-id={artifact.id}>
      <button type="button" onClick={onToggle} className="flex w-full items-start gap-3 text-left" aria-expanded={open}>
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-accent/10 text-accent">
          <ArtifactIcon type={artifact.type} size={18} />
        </span>
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-center gap-2">
            <span className="truncate font-medium" data-testid="artifact-title">
              {artifact.title}
            </span>
            {artifact.status !== "ready" ? (
              <Badge tone={STATUS_TONE[artifact.status]}>{m.artifacts.status[artifact.status]}</Badge>
            ) : null}
          </span>
          <span className="mt-0.5 block truncate text-xs text-ink-faint">{details.join(" · ")}</span>
        </span>
        <ChevronDown size={16} className={cn("mt-2 shrink-0 text-ink-faint transition-transform", open && "rotate-180")} />
      </button>
      {open ? <ArtifactDetails id={artifact.id} onChanged={onChanged} /> : null}
    </Card>
  );
}

function ArtifactDetails({ id, onChanged }: { id: string; onChanged: () => void }) {
  const { status } = useApp();
  const readOnly = status?.deployment_profile === "free-beta";
  const { m, f } = useI18n();
  const fetchDetail = useCallback(() => api.getArtifact(id), [id]);
  const { data: loaded, error } = useApiData(fetchDetail);
  const [updated, setUpdated] = useState<ArtifactDetail | null>(null);
  const detail = updated ?? loaded;
  const [text, setText] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [summary, setSummary] = useState("");
  const [renaming, setRenaming] = useState(false);
  const [title, setTitle] = useState("");
  const [problem, setProblem] = useState<string | null>(null);

  const current = detail?.current_version ?? null;
  const currentNumber = current?.version_number;
  const isText = current?.is_text ?? false;

  useEffect(() => {
    if (!isText || currentNumber === undefined) return;
    let cancelled = false;
    api.artifactText(id, currentNumber).then(
      (result) => !cancelled && setText(result.text),
      () => !cancelled && setText(null),
    );
    return () => {
      cancelled = true;
    };
  }, [id, isText, currentNumber]);

  const run = async (action: () => Promise<ArtifactDetail | void>) => {
    setProblem(null);
    try {
      const result = await action();
      if (result) setUpdated(result);
      onChanged();
    } catch (reason) {
      setProblem(reason instanceof ApiError ? reason.message : String(reason));
    }
  };

  async function download(version: ArtifactVersion) {
    const { blob, filename } = await api.downloadArtifact(id, version.version_number);
    saveBlob(blob, filename);
  }

  function saveEdit(event: FormEvent) {
    event.preventDefault();
    void run(async () => {
      const result = await api.addArtifactVersion(id, draft, summary);
      setEditing(false);
      setSummary("");
      return result;
    });
  }

  function saveTitle(event: FormEvent) {
    event.preventDefault();
    if (!title.trim()) return;
    void run(async () => {
      await api.renameArtifact(id, title.trim());
      setRenaming(false);
      return api.getArtifact(id);
    });
  }

  if (error) return <p className="mt-3 text-sm text-danger">{error.message}</p>;
  if (!detail) return <Spinner className="mt-3" label={m.common.loading} />;

  const noteLabel = (note: string | null) => {
    if (!note) return "";
    if (note === "Created") return m.artifacts.createdNote;
    if (note === "Edited") return m.artifacts.editedNote;
    const restored = /^Restored from version (\d+)$/.exec(note);
    return restored ? f(m.artifacts.restoredFrom, { n: restored[1] ?? "" }) : note;
  };

  const byLabel = (version: ArtifactVersion) =>
    version.created_by === "restore"
      ? m.artifacts.byUser
      : version.created_by.startsWith("agent:")
        ? m.artifacts.byAgent
        : m.artifacts.byUser;

  return (
    <div className="mt-3 border-t border-line pt-3 text-sm" data-testid="artifact-details">
      <div className="flex flex-wrap items-center gap-1.5">
        {current ? (
          <Button variant="secondary" size="sm" onClick={() => void download(current)} data-testid="artifact-download">
            <Download size={14} /> {m.artifacts.download}
          </Button>
        ) : null}
        {isText && !editing && !readOnly ? (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setDraft(text ?? "");
              setEditing(true);
            }}
            data-testid="artifact-edit"
          >
            <Pencil size={14} /> {m.artifacts.edit}
          </Button>
        ) : null}
        <Button
          variant="ghost"
          size="sm"
          disabled={readOnly}
          onClick={() => {
            setTitle(detail.title);
            setRenaming(true);
          }}
        >
          <Type size={14} /> {m.artifacts.rename}
        </Button>
        <Button
          variant="ghost"
          size="sm"
          className="ml-auto text-danger"
          onClick={() => {
            if (window.confirm(f(m.artifacts.confirmDelete, { title: detail.title }))) {
              void run(() => api.deleteArtifact(id));
            }
          }}
          disabled={readOnly}
          data-testid="artifact-delete"
        >
          <Trash2 size={14} /> {m.artifacts.delete}
        </Button>
      </div>

      {current ? <VersionExports artifactId={id} version={current} artifactType={detail.type} /> : null}

      {renaming ? (
        <form onSubmit={saveTitle} className="mt-3 flex gap-2">
          <input
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            aria-label={m.artifacts.rename}
            className="h-9 min-w-0 flex-1 rounded-lg border border-line bg-surface px-3 focus:border-accent/60 focus:outline-none"
            autoFocus
            maxLength={300}
            data-testid="artifact-rename-input"
          />
          <Button type="submit" size="sm">
            <Save size={14} />
          </Button>
          <Button type="button" variant="ghost" size="sm" onClick={() => setRenaming(false)}>
            {m.artifacts.cancel}
          </Button>
        </form>
      ) : null}

      {problem ? (
        <p className="mt-2 text-danger" role="alert">
          {problem}
        </p>
      ) : null}

      {editing ? (
        <form onSubmit={saveEdit} className="mt-3 flex flex-col gap-2">
          <textarea
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            rows={12}
            className="w-full rounded-lg border border-line bg-surface p-3 font-mono text-[13px] leading-relaxed focus:border-accent/60 focus:outline-none"
            aria-label={m.artifacts.edit}
            data-testid="artifact-editor"
          />
          <input
            value={summary}
            onChange={(event) => setSummary(event.target.value)}
            placeholder={m.artifacts.changeSummary}
            maxLength={500}
            className="h-9 rounded-lg border border-line bg-surface px-3 focus:border-accent/60 focus:outline-none"
          />
          <div className="flex gap-2">
            <Button type="submit" size="sm" disabled={!draft.trim() || draft === text} data-testid="artifact-save-version">
              <Save size={14} /> {m.artifacts.saveVersion}
            </Button>
            <Button type="button" variant="ghost" size="sm" onClick={() => setEditing(false)}>
              {m.artifacts.cancel}
            </Button>
          </div>
        </form>
      ) : isText && text !== null ? (
        <pre
          className="mt-3 max-h-64 overflow-auto whitespace-pre-wrap rounded-lg bg-surface-2 p-3 text-[13px] leading-relaxed text-ink-muted"
          data-testid="artifact-preview"
        >
          {text}
        </pre>
      ) : null}

      <p className="mb-1 mt-4 flex items-center gap-1.5 text-xs font-medium uppercase tracking-wider text-ink-faint">
        <History size={13} /> {m.artifacts.versions}
        {detail.source_references.length ? (
          <span className="normal-case tracking-normal">· {f(m.artifacts.sources, { n: detail.source_references.length })}</span>
        ) : null}
      </p>
      <ul className="flex flex-col divide-y divide-line" data-testid="artifact-versions">
        {detail.versions.map((version) => (
          <li key={version.id} className="flex flex-wrap items-center gap-2 py-1.5" data-testid="artifact-version">
            <span className="w-10 font-mono text-xs">{f(m.artifacts.version, { n: version.version_number })}</span>
            <span className="min-w-0 flex-1 text-xs text-ink-muted">
              {new Date(version.created_at).toLocaleString()} · {byLabel(version)}
              {version.change_summary ? ` · ${noteLabel(version.change_summary)}` : ""} · {formatBytes(version.file_size)}
              {version.current ? <span className="text-accent"> · {m.artifacts.current}</span> : null}
            </span>
            <button
              type="button"
              onClick={() => void download(version)}
              className="rounded p-1 text-ink-faint hover:text-ink"
              aria-label={`${m.artifacts.download} v${version.version_number}`}
            >
              <Download size={14} />
            </button>
            {!version.current && !readOnly ? (
              <button
                type="button"
                onClick={() => void run(() => api.restoreArtifactVersion(id, version.version_number))}
                className="rounded px-1.5 py-0.5 text-xs text-ink-faint hover:text-ink"
                data-testid="artifact-restore"
              >
                {m.artifacts.restore}
              </button>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  );
}
