import type { KnowledgeDocument, KnowledgeStatus } from "@ezo/shared";
import { api } from "./api";

export const PENDING_STATUSES: ReadonlySet<KnowledgeStatus> = new Set(["queued", "processing"]);

export function isPending(document: Pick<KnowledgeDocument, "status">): boolean {
  return PENDING_STATUSES.has(document.status);
}

/**
 * Follow a document while the API reads it in the background.
 * Calls `onUpdate` with every new state; stops when processing ends,
 * on timeout, or when `signal` is aborted.
 */
export async function followDocument(
  id: string,
  onUpdate: (document: KnowledgeDocument) => void,
  { signal, intervalMs = 1500, timeoutMs = 180_000 }: { signal?: AbortSignal; intervalMs?: number; timeoutMs?: number } = {},
): Promise<KnowledgeDocument | null> {
  const deadline = Date.now() + timeoutMs;
  while (!signal?.aborted && Date.now() < deadline) {
    await new Promise((resolve) => window.setTimeout(resolve, intervalMs));
    if (signal?.aborted) break;
    try {
      const document = await api.getDocument(id);
      onUpdate(document);
      if (!isPending(document)) return document;
    } catch {
      return null; // deleted or API unavailable; the list view will show the truth on reload
    }
  }
  return null;
}

export function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
