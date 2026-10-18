"use client";

import type { KnowledgeStatus } from "@ezo/shared";
import { ApiError } from "@ezo/shared";
import { Badge } from "@ezo/ui";
import { FileText, Loader2, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n/context";
import { followDocument, isPending } from "@/lib/knowledge";
import { StatusBadge } from "../knowledge/StatusBadge";

export interface Attachment {
  key: string;
  name: string;
  /** Set once the upload is stored; sent with the next message. */
  documentId?: string;
  status: KnowledgeStatus | "uploading";
  /** Problem or note to show (rejected upload, OCR needed, duplicate…). */
  note?: string;
}

/**
 * Files the user dropped into the conversation. They go to EZO's knowledge base
 * (scoped to the current project) and are attached to the next message, in order, so
 * EZO works on exactly these files ("merge these", "translate this").
 */
export function useAttachments(projectId?: string | null) {
  const { m } = useI18n();
  const [items, setItems] = useState<Attachment[]>([]);
  const controllers = useRef(new Set<AbortController>());

  useEffect(() => {
    const active = controllers.current;
    return () => active.forEach((controller) => controller.abort());
  }, []);

  const update = useCallback((key: string, patch: Partial<Attachment>) => {
    setItems((current) => current.map((item) => (item.key === key ? { ...item, ...patch } : item)));
  }, []);

  const attach = useCallback(
    (files: File[]) => {
      for (const file of files) {
        const key = `${file.name}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
        setItems((current) => [...current, { key, name: file.name, status: "uploading" }]);
        void (async () => {
          try {
            const result = await api.uploadDocument(file, file.name, projectId);
            const document = result.document;
            update(key, {
              documentId: document.id,
              status: document.status,
              note: result.duplicate ? m.knowledge.duplicate : (document.error ?? undefined),
            });
            if (isPending(document)) {
              const controller = new AbortController();
              controllers.current.add(controller);
              await followDocument(document.id, (latest) => update(key, { status: latest.status, note: latest.error ?? undefined }), {
                signal: controller.signal,
              });
              controllers.current.delete(controller);
            }
          } catch (error) {
            update(key, { status: "failed", note: error instanceof ApiError ? error.message : String(error) });
          }
        })();
      }
    },
    [m.knowledge.duplicate, projectId, update],
  );

  const dismiss = useCallback((key: string) => setItems((current) => current.filter((item) => item.key !== key)), []);

  /** True while a file has not reached the server yet (sending would lose it). */
  const uploading = items.some((item) => item.status === "uploading");

  /** The stored files to send with a message; they are removed from the composer. */
  const take = useCallback((): { id: string; name: string }[] => {
    const ready = items.filter((item) => item.documentId && item.status !== "failed");
    setItems((current) => current.filter((item) => !ready.includes(item)));
    return ready.map((item) => ({ id: item.documentId!, name: item.name }));
  }, [items]);

  return { items, attach, dismiss, uploading, take };
}

export function AttachmentList({ items, onDismiss }: { items: Attachment[]; onDismiss: (key: string) => void }) {
  const { m } = useI18n();
  if (items.length === 0) return null;
  return (
    <ul className="mb-2 flex flex-wrap gap-2" data-testid="attachments">
      {items.map((item) => (
        <li
          key={item.key}
          className="flex max-w-full items-center gap-2 rounded-xl border border-line bg-surface px-3 py-1.5 text-sm"
          data-testid="attachment"
          title={item.note}
        >
          <FileText size={14} className="shrink-0 text-ink-faint" />
          <span className="max-w-[12rem] truncate">{item.name}</span>
          {item.status === "uploading" ? (
            <Badge tone="accent">
              <Loader2 size={11} className="animate-spin" /> {m.knowledge.uploading}
            </Badge>
          ) : (
            <StatusBadge status={item.status} />
          )}
          {item.note ? <span className="hidden max-w-[16rem] truncate text-xs text-ink-faint sm:inline">{item.note}</span> : null}
          <button
            type="button"
            onClick={() => onDismiss(item.key)}
            className="rounded p-0.5 text-ink-faint hover:text-ink"
            aria-label={m.common.close}
          >
            <X size={13} />
          </button>
        </li>
      ))}
    </ul>
  );
}
