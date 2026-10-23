"use client";

import type { Memory, MemoryCategory } from "@ezo/shared";
import { Button, Card, cn, SelectField, Spinner, TextField } from "@ezo/ui";
import {
  Brain,
  CheckCircle2,
  Download,
  Plus,
  ShieldCheck,
  Target,
  Trash2,
} from "lucide-react";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { api, apiUrl, storedToken } from "@/lib/api";
import { useApp } from "@/lib/app-state";
import { useI18n } from "@/lib/i18n/context";
import { useApiData } from "@/lib/use-api-data";
import { MemoryList } from "./MemoryList";
import { PageFrame } from "./PageFrame";

type Tab = "memories" | "goals";
type Filter = "all" | "profile" | "project";
const CATEGORIES: MemoryCategory[] = [
  "preference",
  "personal",
  "goal",
  "learning",
  "decision",
  "fact",
];

interface PersonalGoal {
  id: string;
  title: string;
  category: string;
  target_date: string | null;
  progress: number;
  status: "active" | "completed" | "paused" | "archived";
  created_at: string;
}

interface PersonalProfile {
  user_id: string;
  email: string;
  memory_consent: boolean;
  auto_memory: boolean;
  memory_stats: { total_count: number };
  goals_stats: { total_count: number; active_count: number; completed_count: number };
}

export function MemoryPage() {
  const { m } = useI18n();
  // Free beta refuses automatic capture (409), so consent there covers explicit saves only.
  const freeBeta = useApp().status?.deployment_profile === "free-beta";
  const [activeTab, setActiveTab] = useState<Tab>("memories");
  const [filter, setFilter] = useState<Filter>("all");

  // Profile and consent state
  const [profile, setProfile] = useState<PersonalProfile | null>(null);
  const [consentLoading, setConsentLoading] = useState(false);

  // Goals state
  const [goals, setGoals] = useState<PersonalGoal[] | null>(null);
  const [newGoalTitle, setNewGoalTitle] = useState("");
  const [newGoalCategory, setNewGoalCategory] = useState("career");
  const [refreshIndex, setRefreshIndex] = useState(0);
  const refresh = useCallback(() => setRefreshIndex((v) => v + 1), []);

  // Memory fetcher
  const fetchMemories = useCallback(
    () => api.listMemories(filter === "all" ? {} : { memoryType: filter }),
    [filter],
  );
  const { data: memories, error: loadError, reload: reloadMemories } = useApiData(fetchMemories);
  const [actionError, setError] = useState<string | null>(null);
  const error = actionError ?? loadError?.message ?? null;
  const [content, setContent] = useState("");
  const [category, setCategory] = useState<MemoryCategory>("preference");

  const authHeaders = useCallback(() => {
    const token = storedToken.get().trim();
    return {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    const headers = authHeaders();

    fetch(`${apiUrl()}/api/personal/profile`, { headers })
      .then((res) => (res.ok ? res.json() : null))
      .then((data: PersonalProfile | null) => {
        if (!cancelled && data) setProfile(data);
      })
      .catch(() => {});

    fetch(`${apiUrl()}/api/personal/goals`, { headers })
      .then((res) => (res.ok ? res.json() : null))
      .then((data: PersonalGoal[] | null) => {
        if (!cancelled && data) setGoals(data);
      })
      .catch(() => {});

    return () => {
      cancelled = true;
    };
  }, [authHeaders, refreshIndex]);

  async function toggleConsent() {
    if (!profile) return;
    setConsentLoading(true);
    const nextConsent = !profile.memory_consent;
    const nextAuto = nextConsent && !freeBeta;
    try {
      const res = await fetch(`${apiUrl()}/api/personal/consent`, {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify({ consent: nextConsent, auto_memory: nextAuto }),
      });
      if (res.ok) {
        setProfile((prev) =>
          prev ? { ...prev, memory_consent: nextConsent, auto_memory: nextAuto } : null,
        );
      } else {
        setError(`Rozilik o‘zgarmadi (${res.status}).`);
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setConsentLoading(false);
    }
  }

  async function addGoal(event: FormEvent) {
    event.preventDefault();
    if (!newGoalTitle.trim()) return;
    try {
      const res = await fetch(`${apiUrl()}/api/personal/goals`, {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify({
          title: newGoalTitle.trim(),
          category: newGoalCategory,
          progress: 0.0,
        }),
      });
      if (res.ok) {
        setNewGoalTitle("");
        refresh();
      } else {
        setError(`Maqsad saqlanmadi (${res.status}).`);
      }
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function updateGoalProgress(goalId: string, progress: number) {
    try {
      await fetch(`${apiUrl()}/api/personal/goals/${goalId}`, {
        method: "PATCH",
        headers: authHeaders(),
        body: JSON.stringify({
          progress,
          status: progress >= 1.0 ? "completed" : "active",
        }),
      });
      refresh();
    } catch {
      // Handled silently
    }
  }

  async function deleteGoal(goalId: string) {
    if (!window.confirm(m.common.confirmDelete)) return;
    try {
      await fetch(`${apiUrl()}/api/personal/goals/${goalId}`, {
        method: "DELETE",
        headers: authHeaders(),
      });
      refresh();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function exportMemories() {
    try {
      const res = await fetch(`${apiUrl()}/api/personal/memories/export`, {
        headers: authHeaders(),
      });
      if (res.ok) {
        const data = (await res.json()) as { markdown: string };
        const blob = new Blob([data.markdown], { type: "text/markdown;charset=utf-8" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `ezo-xotiralari-${new Date().toISOString().split("T")[0]}.md`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
      }
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function addMemory(event: FormEvent) {
    event.preventDefault();
    if (content.trim().length < 2) return;
    try {
      await api.createMemory({ content: content.trim(), category });
      setContent("");
      setError(null);
      reloadMemories();
      refresh();
    } catch (reason) {
      setError((reason as Error).message);
    }
  }

  async function removeMemory(memory: Memory) {
    await api.deleteMemory(memory.id);
    reloadMemories();
    refresh();
  }

  async function removeAllMemories() {
    if (!window.confirm(m.memory.deleteAllConfirm)) return;
    await api.deleteAllMemories();
    reloadMemories();
    refresh();
  }

  const filters: { key: Filter; label: string }[] = [
    { key: "all", label: m.memory.all },
    { key: "profile", label: m.memory.profile },
    { key: "project", label: m.memory.project },
  ];
  const categories = m.memory.categories as Record<string, string>;

  return (
    <PageFrame
      title={m.personal?.title ?? m.memory.title}
      subtitle={m.personal?.subtitle ?? m.memory.subtitle}
      actions={
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            icon={<Download size={14} />}
            onClick={() => void exportMemories()}
          >
            {m.personal?.exportData ?? "Eksport"}
          </Button>
          {memories && memories.length > 0 ? (
            <Button
              variant="danger"
              size="sm"
              icon={<Trash2 size={14} />}
              onClick={() => void removeAllMemories()}
            >
              {m.memory.deleteAll}
            </Button>
          ) : null}
        </div>
      }
    >
      {/* Privacy & Opt-in Consent Banner */}
      <Card className="mb-6 border-accent/20 bg-accent/5">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-start gap-3">
            <div className="rounded-xl bg-accent/10 p-2.5 text-accent">
              <ShieldCheck size={24} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-sm font-semibold text-ink">
                  {m.personal?.consentTitle ?? "Xotira saqlashga rozilik (Opt-in)"}
                </h2>
                <span
                  className={cn(
                    "rounded-full px-2 py-0.5 text-xs font-medium",
                    profile?.memory_consent
                      ? "bg-accent/20 text-accent"
                      : "bg-surface-3 text-ink-muted",
                  )}
                  data-testid="memory-consent-badge"
                >
                  {profile?.memory_consent
                    ? m.personal?.consentGranted ?? "Faol"
                    : m.personal?.consentRevoked ?? "O'chiq"}
                </span>
              </div>
              <p className="mt-1 text-xs leading-relaxed text-ink-muted">
                {m.personal?.consentDesc ??
                  "EZO faqat siz ruxsat berganingizdagina suhbatlar mazmunidan muhim faktlarni xotirada saqlaydi. Hech qanday yashirin to'plash bo'lmaydi."}
              </p>
            </div>
          </div>
          <Button
            variant={profile?.memory_consent ? "ghost" : "primary"}
            size="sm"
            disabled={consentLoading || profile === null}
            onClick={() => void toggleConsent()}
            data-testid="memory-consent-toggle"
          >
            {consentLoading ? (
              <Spinner />
            ) : profile?.memory_consent ? (
              m.personal?.revokeConsent ?? "To'xtatish"
            ) : (
              m.personal?.grantConsent ?? "Ruxsat berish"
            )}
          </Button>
        </div>
      </Card>

      {/* Intelligence Stats Overview */}
      <div className="mb-6 grid grid-cols-1 gap-3 sm:grid-cols-3">
        <div className="flex items-center gap-3 rounded-xl border border-line bg-surface p-3.5">
          <div className="rounded-lg bg-surface-2 p-2 text-accent">
            <Brain size={20} />
          </div>
          <div>
            <p className="text-xs text-ink-muted">{m.personal?.totalMemories ?? "Xotiralar"}</p>
            <p className="text-lg font-semibold text-ink">
              {profile?.memory_stats?.total_count ?? memories?.length ?? 0}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3 rounded-xl border border-line bg-surface p-3.5">
          <div className="rounded-lg bg-surface-2 p-2 text-accent2">
            <Target size={20} />
          </div>
          <div>
            <p className="text-xs text-ink-muted">{m.personal?.activeGoals ?? "Faol maqsadlar"}</p>
            <p className="text-lg font-semibold text-ink">
              {profile?.goals_stats?.active_count ?? (goals?.filter((g) => g.status === "active").length ?? 0)}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3 rounded-xl border border-line bg-surface p-3.5">
          <div className="rounded-lg bg-surface-2 p-2 text-success">
            <CheckCircle2 size={20} />
          </div>
          <div>
            <p className="text-xs text-ink-muted">
              {m.personal?.learningScore ?? "Tugallangan maqsadlar"}
            </p>
            <p className="text-lg font-semibold text-ink">
              {profile?.goals_stats?.completed_count ??
                (goals?.filter((g) => g.status === "completed").length ?? 0)}
            </p>
          </div>
        </div>
      </div>

      {/* Primary Tabs: Memories vs Goals */}
      <div className="mb-6 flex gap-2 border-b border-line pb-2" role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === "memories"}
          onClick={() => setActiveTab("memories")}
          className={cn(
            "flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors",
            activeTab === "memories"
              ? "bg-surface-2 text-ink"
              : "text-ink-muted hover:bg-surface-2/60 hover:text-ink",
          )}
        >
          <Brain size={16} />
          {m.memory.title}
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === "goals"}
          onClick={() => setActiveTab("goals")}
          className={cn(
            "flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors",
            activeTab === "goals"
              ? "bg-surface-2 text-ink"
              : "text-ink-muted hover:bg-surface-2/60 hover:text-ink",
          )}
        >
          <Target size={16} />
          {m.personal?.goalsTitle ?? "Shaxsiy maqsadlar"}
        </button>
      </div>

      {activeTab === "memories" ? (
        <>
          <Card className="mb-6">
            <form
              onSubmit={addMemory}
              className="flex flex-col gap-3 sm:flex-row sm:items-end"
              data-testid="memory-form"
            >
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
                <SelectField
                  label=" "
                  aria-label="category"
                  value={category}
                  onChange={(e) => setCategory(e.target.value as MemoryCategory)}
                >
                  {CATEGORIES.map((key) => (
                    <option key={key} value={key}>
                      {categories[key]}
                    </option>
                  ))}
                </SelectField>
              </div>
              <Button
                type="submit"
                variant="primary"
                icon={<Plus size={16} />}
                disabled={content.trim().length < 2}
              >
                {m.memory.add}
              </Button>
            </form>
          </Card>

          <div
            className="mb-4 flex gap-1 rounded-xl border border-line bg-surface p-1 text-sm"
            role="tablist"
          >
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
          {memories?.length === 0 ? (
            <p className="text-sm text-ink-muted">{m.memory.empty}</p>
          ) : null}
          {memories && memories.length > 0 ? (
            <MemoryList memories={memories} onDelete={(memory) => void removeMemory(memory)} />
          ) : null}
        </>
      ) : (
        /* Goals Tab */
        <div className="space-y-6">
          <Card>
            <form onSubmit={addGoal} className="flex flex-col gap-3 sm:flex-row sm:items-end">
              <div className="flex-1">
                <TextField
                  label={m.personal?.addGoal ?? "Yangi maqsad"}
                  placeholder="Masalan: IELTS 7.5 olish yoki Python kitobini yakunlash"
                  value={newGoalTitle}
                  onChange={(e) => setNewGoalTitle(e.target.value)}
                  maxLength={200}
                />
              </div>
              <div className="sm:w-44">
                <SelectField
                  label="Kategoriya"
                  value={newGoalCategory}
                  onChange={(e) => setNewGoalCategory(e.target.value)}
                >
                  <option value="learning">Ta&apos;lim</option>
                  <option value="career">Karyera</option>
                  <option value="language">Til</option>
                  <option value="productivity">Samaradorlik</option>
                  <option value="personal">Shaxsiy</option>
                  <option value="other">Boshqa</option>
                </SelectField>
              </div>
              <Button
                type="submit"
                variant="primary"
                icon={<Plus size={16} />}
                disabled={!newGoalTitle.trim()}
              >
                {m.common.create}
              </Button>
            </form>
          </Card>

          {goals === null ? <Spinner label={m.common.loading} /> : null}
          {goals?.length === 0 ? (
            <p className="text-sm text-ink-muted">
              {m.personal?.noGoals ?? "Hozircha maqsadlar kiritilmagan."}
            </p>
          ) : null}

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {goals?.map((goal) => {
              const percent = Math.round(goal.progress * 100);
              return (
                <Card key={goal.id} className="relative flex flex-col justify-between gap-4">
                  <div>
                    <div className="flex items-start justify-between gap-2">
                      <span className="rounded-md bg-surface-2 px-2 py-0.5 text-xs font-medium uppercase tracking-wider text-ink-muted">
                        {goal.category}
                      </span>
                      <button
                        type="button"
                        onClick={() => void deleteGoal(goal.id)}
                        className="rounded p-1 text-ink-faint hover:text-danger"
                        title={m.common.delete}
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                    <h3 className="mt-2 text-base font-semibold text-ink">{goal.title}</h3>
                  </div>

                  <div className="space-y-2">
                    <div className="flex items-center justify-between text-xs text-ink-muted">
                      <span>{m.personal?.progress ?? "Rivojlanish"}</span>
                      <span className="font-semibold text-ink">{percent}%</span>
                    </div>
                    <div className="h-2 w-full overflow-hidden rounded-full bg-surface-2">
                      <div
                        className="h-full bg-accent transition-all duration-300"
                        style={{ width: `${percent}%` }}
                      />
                    </div>
                    <div className="flex items-center gap-2 pt-2">
                      <button
                        type="button"
                        onClick={() =>
                          void updateGoalProgress(
                            goal.id,
                            Math.min(1.0, Math.round((goal.progress + 0.25) * 100) / 100),
                          )
                        }
                        className="rounded-lg border border-line bg-surface px-2.5 py-1 text-xs font-medium text-ink transition-colors hover:border-accent/40"
                      >
                        +25%
                      </button>
                      <button
                        type="button"
                        onClick={() => void updateGoalProgress(goal.id, 1.0)}
                        className="rounded-lg border border-line bg-surface px-2.5 py-1 text-xs font-medium text-ink transition-colors hover:border-accent/40"
                      >
                        100% (Bajarildi)
                      </button>
                    </div>
                  </div>
                </Card>
              );
            })}
          </div>
        </div>
      )}
    </PageFrame>
  );
}
