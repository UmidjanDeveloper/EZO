"use client";

import type { Memory, MemoryCategory } from "@ezo/shared";
import { Button, Card, cn, SelectField, Spinner, TextField } from "@ezo/ui";
import { Plus, Trash2 } from "lucide-react";
import { useCallback, useState, type FormEvent } from "react";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n/context";
import { useApiData } from "@/lib/use-api-data";
import { MemoryList } from "./MemoryList";
import { PageFrame } from "./PageFrame";

type Filter = "all" | "profile" | "project";
const CATEGORIES: MemoryCategory[] = ["preference", "personal", "goal", "learning", "decision", "fact"];

export function MemoryPage() {
  const { m } = useI18n();
  const [filter, setFilter] = useState<Filter>("all");
  const fetchMemories = useCallback(
    () => api.listMemories(filter === "all" ? {} : { memoryType: filter }),
    [filter],
  );
  const { data: memories, error: loadError, reload } = useApiData(fetchMemories);
  const [actionError, setError] = useState<string | null>(null);
  const error = actionError ?? loadError?.message ?? null;
  const [content, setContent] = useState("");
  const [category, setCategory] = useState<MemoryCategory>("preference");

  async function add(event: FormEvent) {
    event.preventDefault();
    if (content.trim().length < 2) return;
    try {
      await api.createMemory({ content: content.trim(), category });
      setContent("");
      setError(null);
      reload();
    } catch (reason) {
      setError((reason as Error).message);
    }
  }

  async function remove(memory: Memory) {
    await api.deleteMemory(memory.id);
    reload();
  }

  async function removeAll() {
    if (!window.confirm(m.memory.deleteAllConfirm)) return;
    await api.deleteAllMemories();
    reload();
  }

  const filters: { key: Filter; label: string }[] = [
    { key: "all", label: m.memory.all },
    { key: "profile", label: m.memory.profile },
    { key: "project", label: m.memory.project },
  ];
  const categories = m.memory.categories as Record<string, string>;

  return (
    <PageFrame
      title={m.memory.title}
      subtitle={m.memory.subtitle}
      actions={
        memories && memories.length > 0 ? (
          <Button variant="danger" size="sm" icon={<Trash2 size={14} />} onClick={() => void removeAll()}>
            {m.memory.deleteAll}
          </Button>
        ) : null
      }
    >
      <Card className="mb-6">
        <form onSubmit={add} className="flex flex-col gap-3 sm:flex-row sm:items-end" data-testid="memory-form">
          <div className="flex-1">
            <TextField
              label={m.memory.add}
              placeholder={m.memory.addPlaceholder}
              value={content}
              onChange={(e) => setContent(e.target.value)}
              maxLength={1000}
            />
          </div>
          <div className="sm:w-44">
            <SelectField label=" " aria-label="category" value={category} onChange={(e) => setCategory(e.target.value as MemoryCategory)}>
              {CATEGORIES.map((key) => (
                <option key={key} value={key}>
                  {categories[key]}
                </option>
              ))}
            </SelectField>
          </div>
          <Button type="submit" variant="primary" icon={<Plus size={16} />} disabled={content.trim().length < 2}>
            {m.memory.add}
          </Button>
        </form>
      </Card>

      <div className="mb-4 flex gap-1 rounded-xl border border-line bg-surface p-1 text-sm" role="tablist">
        {filters.map((item) => (
          <button
            key={item.key}
            type="button"
            role="tab"
            aria-selected={filter === item.key}
            onClick={() => setFilter(item.key)}
            className={cn(
              "flex-1 rounded-lg px-3 py-1.5 transition-colors",
              filter === item.key ? "bg-surface-2 text-ink" : "text-ink-muted hover:text-ink",
            )}
          >
            {item.label}
          </button>
        ))}
      </div>

      {error ? <p className="mb-4 text-sm text-danger">{error}</p> : null}
      {memories === null && !error ? <Spinner label={m.common.loading} /> : null}
      {memories?.length === 0 ? <p className="text-sm text-ink-muted">{m.memory.empty}</p> : null}
      {memories && memories.length > 0 ? <MemoryList memories={memories} onDelete={(memory) => void remove(memory)} /> : null}
    </PageFrame>
  );
}
