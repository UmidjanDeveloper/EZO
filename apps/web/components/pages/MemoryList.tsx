"use client";

import type { Memory } from "@ezo/shared";
import { Badge } from "@ezo/ui";
import { ShieldAlert, Trash2 } from "lucide-react";
import { useI18n } from "@/lib/i18n/context";

export function MemoryList({ memories, onDelete }: { memories: Memory[]; onDelete: (memory: Memory) => void }) {
  const { m, language } = useI18n();
  const categories = m.memory.categories as Record<string, string>;
  return (
    <ul className="flex flex-col gap-2" data-testid="memory-list">
      {memories.map((memory) => (
        <li key={memory.id} className="flex items-start gap-3 rounded-xl border border-line bg-surface px-4 py-3">
          <div className="min-w-0 flex-1">
            <p className="break-words text-[15px]">{memory.content}</p>
            <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-xs text-ink-faint">
              <Badge tone={memory.memory_type === "project" ? "accent" : "neutral"}>
                {memory.memory_type === "project" ? m.memory.project : m.memory.profile}
              </Badge>
              <Badge>{categories[memory.category] ?? memory.category}</Badge>
              {memory.sensitive ? (
                <Badge tone="warning">
                  <ShieldAlert size={12} /> {m.memory.sensitive}
                </Badge>
              ) : null}
              <span>
                {m.memory.importance}: {Math.round(memory.importance * 100)}%
              </span>
              <span>· {memory.source === "auto" ? m.memory.sourceAuto : m.memory.sourceUser}</span>
              <span>· {new Date(memory.updated_at).toLocaleDateString(language)}</span>
            </div>
          </div>
          <button
            type="button"
            onClick={() => onDelete(memory)}
            className="rounded-lg p-1.5 text-ink-faint hover:bg-danger/10 hover:text-danger"
            aria-label={`${m.common.delete}: ${memory.content}`}
          >
            <Trash2 size={16} />
          </button>
        </li>
      ))}
    </ul>
  );
}
