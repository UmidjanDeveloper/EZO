"use client";

import type { KnowledgeDocument, KnowledgeDocumentDetail } from "@ezo/shared";
import { ApiError } from "@ezo/shared";
import { Button, Card, cn, Spinner } from "@ezo/ui";
import { ChevronDown, FileText, Globe, Link2, RotateCw, Trash2, Upload } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type DragEvent, type FormEvent } from "react";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n/context";
import { formatSize, isPending } from "@/lib/knowledge";
import { useApiData } from "@/lib/use-api-data";
import { PageFrame } from "../pages/PageFrame";
import { StatusBadge } from "./StatusBadge";

type Notice = { tone: "info" | "error"; text: string } | null;

export function KnowledgePage() {
  const { m, f } = useI18n();
  const fetchDocuments = useCallback(() => api.listDocuments(), []);
  const { data: documents, error: loadError, reload } = useApiData(fetchDocuments);
  const fetchOverview = useCallback(() => api.knowledgeStatus(), []);
  const { data: overview } = useApiData(fetchOverview);

  const [notice, setNotice] = useState<Notice>(null);
  const [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [url, setUrl] = useState("");
  const [openId, setOpenId] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // While something is being read in the background, refresh the list.
  const pending = documents?.some(isPending) ?? false;
  useEffect(() => {
    if (!pending) return;
    const timer = window.setTimeout(reload, 1500);
    return () => window.clearTimeout(timer);
  }, [pending, documents, reload]);

  function describe(result: { duplicate: boolean; new_revision: boolean; document: KnowledgeDocument }): Notice {
    if (result.duplicate) return { tone: "info", text: m.knowledge.duplicate };
    if (result.new_revision) return { tone: "info", text: f(m.knowledge.newRevision, { n: result.document.current_revision ?? 1 }) };
    return null;
  }

  async function upload(files: FileList | File[]) {
    setBusy(true);
    setNotice(null);
    try {
      for (const file of Array.from(files)) {
        const result = await api.uploadDocument(file, file.name);
        setNotice(describe(result));
      }
    } catch (error) {
      setNotice({ tone: "error", text: error instanceof ApiError ? error.message : String(error) });
    } finally {
      setBusy(false);
      if (inputRef.current) inputRef.current.value = "";
      reload();
    }
  }

  async function addUrl(event: FormEvent) {
    event.preventDefault();
    const value = url.trim();
    if (!value) return;
    setBusy(true);
    setNotice(null);
    try {
      setNotice(describe(await api.addUrl(value)));
      setUrl("");
    } catch (error) {
      setNotice({ tone: "error", text: error instanceof ApiError ? error.message : String(error) });
    } finally {
      setBusy(false);
      reload();
    }
  }

  async function remove(document: KnowledgeDocument) {
    if (!window.confirm(f(m.knowledge.confirmDelete, { title: document.title }))) return;
    await api.deleteDocument(document.id);
    reload();
  }

  async function reindex(document: KnowledgeDocument) {
    try {
      await api.reindexDocument(document.id);
    } catch (error) {
      setNotice({ tone: "error", text: error instanceof ApiError ? error.message : String(error) });
    }
    reload();
  }

  function onDrop(event: DragEvent) {
    event.preventDefault();
    setDragging(false);
    if (event.dataTransfer.files.length) void upload(event.dataTransfer.files);
  }

  const allowed = overview?.allowed_extensions.map((ext) => ext.replace(".", "").toUpperCase()).join(", ");

  return (
    <PageFrame title={m.knowledge.title} subtitle={m.knowledge.subtitle}>
      {overview && !overview.semantic_search ? (
        <p className="mb-4 rounded-xl border border-warning/40 bg-warning/5 px-4 py-2.5 text-sm" data-testid="semantic-off">
          {m.knowledge.semanticOff}
        </p>
      ) : null}

      <label
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={cn(
          "flex cursor-pointer flex-col items-center justify-center gap-2 rounded-2xl border-2 border-dashed px-6 py-8 text-center transition-colors",
          dragging ? "border-accent bg-accent/5" : "border-line hover:border-accent/50",
        )}
        data-testid="knowledge-dropzone"
      >
        {busy ? <Spinner label={m.knowledge.uploading} /> : <Upload size={22} className="text-accent" />}
        <span className="text-sm font-medium">{m.knowledge.dropHere}</span>
        {overview ? (
          <span className="text-xs text-ink-faint">{f(m.knowledge.allowed, { types: allowed ?? "", mb: overview.max_upload_mb })}</span>
        ) : null}
        <input
          ref={inputRef}
          type="file"
          multiple
          className="sr-only"
          accept={overview?.allowed_extensions.join(",")}
          onChange={(event) => event.target.files && void upload(event.target.files)}
          data-testid="knowledge-file-input"
          disabled={busy}
        />
      </label>

      <form onSubmit={addUrl} className="mt-3 flex gap-2">
        <label htmlFor="knowledge-url" className="sr-only">
          {m.knowledge.addUrl}
        </label>
        <input
          id="knowledge-url"
          type="url"
          value={url}
          onChange={(event) => setUrl(event.target.value)}
          placeholder={m.knowledge.urlPlaceholder}
          className="h-10 min-w-0 flex-1 rounded-xl border border-line bg-surface px-3 text-sm focus:border-accent/60 focus:outline-none"
        />
        <Button type="submit" variant="secondary" disabled={busy || !url.trim()}>
          <Link2 size={16} /> {m.knowledge.addUrl}
        </Button>
      </form>

      {notice ? (
        <p
          className={cn("mt-3 text-sm", notice.tone === "error" ? "text-danger" : "text-ink-muted")}
          role={notice.tone === "error" ? "alert" : "status"}
          data-testid="knowledge-notice"
        >
          {notice.text}
        </p>
      ) : null}

      <div className="mt-6 flex flex-col gap-2" data-testid="knowledge-list">
        {loadError ? (
          <p className="text-sm text-danger">{loadError.message}</p>
        ) : !documents ? (
          <Spinner label={m.common.loading} />
        ) : documents.length === 0 ? (
          <p className="py-6 text-center text-sm text-ink-muted">{m.knowledge.empty}</p>
        ) : (
          documents.map((document) => (
            <DocumentRow
              key={document.id}
              document={document}
              open={openId === document.id}
              onToggle={() => setOpenId(openId === document.id ? null : document.id)}
              onReindex={() => void reindex(document)}
              onDelete={() => void remove(document)}
            />
          ))
        )}
      </div>
    </PageFrame>
  );
}

function DocumentRow({
  document,
  open,
  onToggle,
  onReindex,
  onDelete,
}: {
  document: KnowledgeDocument;
  open: boolean;
  onToggle: () => void;
  onReindex: () => void;
  onDelete: () => void;
}) {
  const { m, f } = useI18n();
  const Icon = document.source_type === "url" ? Globe : FileText;
  const details = [
    document.source_type === "url" ? document.source_url : document.filename,
    document.size_bytes ? formatSize(document.size_bytes) : null,
    document.chunk_count ? f(m.knowledge.chunks, { n: document.chunk_count }) : null,
    document.current_revision ? f(m.knowledge.revision, { n: document.current_revision }) : null,
  ].filter(Boolean);

  return (
    <Card className="px-4 py-3" data-testid="knowledge-document">
      <div className="flex items-start gap-3">
        <Icon size={18} className="mt-0.5 shrink-0 text-ink-faint" />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="truncate font-medium" data-testid="knowledge-title">
              {document.title}
            </span>
            <StatusBadge status={document.status} />
          </div>
          <p className="mt-0.5 truncate text-xs text-ink-faint">{details.join(" · ")}</p>
          {document.error ? <p className="mt-1 text-sm text-ink-muted">{document.error}</p> : null}
        </div>
        <div className="flex shrink-0 items-center gap-0.5">
          <Button variant="ghost" size="icon" onClick={onReindex} aria-label={m.knowledge.reindex} title={m.knowledge.reindex} disabled={isPending(document)}>
            <RotateCw size={15} />
          </Button>
          <Button variant="ghost" size="icon" onClick={onDelete} aria-label={m.knowledge.delete} title={m.knowledge.delete} data-testid="knowledge-delete">
            <Trash2 size={15} />
          </Button>
          <Button variant="ghost" size="icon" onClick={onToggle} aria-expanded={open} aria-label={m.knowledge.preview}>
            <ChevronDown size={16} className={cn("transition-transform", open && "rotate-180")} />
          </Button>
        </div>
      </div>
      {open ? <DocumentDetails id={document.id} /> : null}
    </Card>
  );
}

function DocumentDetails({ id }: { id: string }) {
  const { m, f } = useI18n();
  const fetchDetail = useCallback(() => api.getDocument(id), [id]);
  const { data, error } = useApiData<KnowledgeDocumentDetail>(fetchDetail);
  if (error) return <p className="mt-3 text-sm text-danger">{error.message}</p>;
  if (!data) return <Spinner className="mt-3" label={m.common.loading} />;
  return (
    <div className="mt-3 grid gap-4 border-t border-line pt-3 text-sm sm:grid-cols-[10rem_1fr]">
      <div>
        <p className="mb-1 text-xs font-medium uppercase tracking-wider text-ink-faint">{m.knowledge.revisions}</p>
        <ul className="space-y-0.5">
          {data.revisions.map((revision) => (
            <li key={revision.id} className="text-ink-muted">
              {f(m.knowledge.revision, { n: revision.revision_number })} · {new Date(revision.created_at).toLocaleDateString()}
              {revision.current ? <span className="text-accent"> · {m.knowledge.current}</span> : null}
            </li>
          ))}
        </ul>
      </div>
      <div className="min-w-0">
        <p className="mb-1 text-xs font-medium uppercase tracking-wider text-ink-faint">{m.knowledge.preview}</p>
        <div className="space-y-2">
          {data.chunks_preview.slice(0, 3).map((chunk) => (
            <p key={chunk.chunk_index} className="line-clamp-4 rounded-lg bg-surface-2 px-3 py-2 text-ink-muted">
              {chunk.text}
            </p>
          ))}
        </div>
      </div>
    </div>
  );
}
