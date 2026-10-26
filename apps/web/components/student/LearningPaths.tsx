"use client";

import { Badge, Button, Card } from "@ezo/ui";
import { useCallback, useEffect, useState } from "react";
import { useI18n } from "@/lib/i18n/context";
import { studentRequest } from "@/lib/student-api";

/** GET /student/learning-paths: owner-defined recall paths; the server evaluates them. */
interface PathSummary {
  id: string;
  title: string;
  state: "active" | "paused";
  version: number;
  created_at: string;
}

interface PathDetail extends PathSummary {
  steps: {
    index: number;
    title: string;
    state: "checkpoint_met" | "practice_needed" | "blocked_by_prerequisite" | "source_unavailable" | "review_budget_exhausted";
    required_recalls: number;
    source_cards: number;
    total_cards: number;
    checkpoint_cards: number;
  }[];
  checkpoint_steps: number;
  total_steps: number;
  recommendations: { step: number; action: "review_card" | "read_source"; card_id: string; due_at: string; reason: string }[];
  mastery_claim: false;
}

interface CardOption {
  id: string;
  front: string;
}

interface DraftStep {
  title: string;
  cardIds: string[];
}

export function LearningPaths({ cards, projectId }: { cards: CardOption[]; projectId: string | null }) {
  const { m, f, language } = useI18n();
  const t = m.studentExtras.paths;
  const [paths, setPaths] = useState<PathSummary[]>([]);
  const [detail, setDetail] = useState<PathDetail | null>(null);
  const [title, setTitle] = useState("");
  const [steps, setSteps] = useState<DraftStep[]>([{ title: "", cardIds: [] }]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const query = projectId ? `?project_id=${encodeURIComponent(projectId)}` : "";

  const load = useCallback(
    () =>
      studentRequest<PathSummary[]>(`student/learning-paths${query}`)
        .then(setPaths)
        .catch((e: Error) => setError(e.message)),
    [query],
  );

  useEffect(() => {
    void load();
  }, [load]);

  const open = async (id: string) => {
    try {
      setDetail(await studentRequest<PathDetail>(`student/learning-paths/${id}${query}`));
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const create = async () => {
    const body = {
      request_id: crypto.randomUUID(),
      project_id: projectId,
      title: title.trim(),
      language,
      steps: steps
        .filter((s) => s.title.trim() && s.cardIds.length)
        .map((s, index) => ({ title: s.title.trim(), card_ids: s.cardIds, prerequisites: index ? [index - 1] : [], required_recalls: 1 })),
    };
    if (!body.title || body.steps.length === 0) return setError(t.needCards);
    setBusy(true);
    setError("");
    try {
      await studentRequest("student/learning-paths", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      setTitle("");
      setSteps([{ title: "", cardIds: [] }]);
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const setState = async (path: PathSummary, state: "active" | "paused") => {
    try {
      await studentRequest(`student/learning-paths/${path.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project_id: projectId, expected_version: path.version, state }),
      });
      await load();
      if (detail?.id === path.id) await open(path.id);
    } catch (e) {
      setError((e as Error).message.includes("changed") ? t.conflict : (e as Error).message);
    }
  };

  const remove = async (path: PathSummary) => {
    if (!window.confirm(t.confirmRemove)) return;
    try {
      await studentRequest(`student/learning-paths/${path.id}${query ? `${query}&` : "?"}confirm=true`, { method: "DELETE" });
      if (detail?.id === path.id) setDetail(null);
      await load();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <Card className="flex flex-col gap-4 p-5" data-testid="learning-paths">
      <div>
        <h3 className="font-semibold text-ink">{t.title}</h3>
        <p className="mt-0.5 text-xs text-ink-muted">{t.note}</p>
      </div>
      {error ? <p className="text-sm text-danger" role="alert">{error}</p> : null}

      {paths.length === 0 ? <p className="text-sm text-ink-muted">{t.none}</p> : null}
      <ul className="flex flex-col gap-2">
        {paths.map((path) => (
          <li key={path.id} className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-line bg-surface px-3 py-2" data-testid="learning-path">
            <span className="text-sm text-ink">
              {path.title} <Badge tone={path.state === "active" ? "success" : "neutral"}>{t.state[path.state]}</Badge>
            </span>
            <span className="flex gap-2">
              <Button size="sm" variant="secondary" onClick={() => void open(path.id)}>{t.open}</Button>
              <Button size="sm" variant="secondary" onClick={() => void setState(path, path.state === "active" ? "paused" : "active")}>
                {path.state === "active" ? t.pause : t.resume}
              </Button>
              <Button size="sm" variant="secondary" onClick={() => void remove(path)}>{t.remove}</Button>
            </span>
          </li>
        ))}
      </ul>

      {detail ? (
        <div className="rounded-xl border border-line bg-surface-2 p-3 text-sm" data-testid="learning-path-detail">
          <div className="flex items-center justify-between">
            <strong>{detail.title}</strong>
            <Button size="sm" variant="secondary" onClick={() => setDetail(null)}>{t.close}</Button>
          </div>
          <p className="mt-1 text-xs text-ink-muted">{f(t.progress, { done: detail.checkpoint_steps, total: detail.total_steps })}</p>
          <ol className="mt-2 flex flex-col gap-1.5">
            {detail.steps.map((step) => (
              <li key={step.index} className="rounded-lg border border-line bg-surface px-3 py-2">
                <div className="flex items-center justify-between gap-2">
                  <span>{step.index + 1}. {step.title}</span>
                  <Badge tone={step.state === "checkpoint_met" ? "success" : step.state === "practice_needed" ? "accent" : "danger"}>{t.stepState[step.state]}</Badge>
                </div>
                <p className="text-xs text-ink-muted">{f(t.cards, { have: step.source_cards, total: step.total_cards, checkpoints: step.checkpoint_cards })}</p>
              </li>
            ))}
          </ol>
          <h4 className="mt-3 text-xs font-medium uppercase tracking-wide text-ink-muted">{t.recommendations}</h4>
          {detail.recommendations.length === 0 ? (
            <p className="text-xs text-ink-muted">{t.noRecommendations}</p>
          ) : (
            <ul className="mt-1 flex flex-col gap-1 text-xs">
              {detail.recommendations.map((r) => (
                <li key={r.card_id}>
                  {r.action === "review_card" ? t.review_card : t.read_source}: {cards.find((c) => c.id === r.card_id)?.front ?? r.card_id.slice(0, 8)}
                </li>
              ))}
            </ul>
          )}
          <p className="mt-2 text-xs text-ink-faint">{t.evidence}</p>
        </div>
      ) : null}

      <div className="flex flex-col gap-2 rounded-xl border border-dashed border-line p-3">
        <input
          className="rounded-lg border border-line bg-surface px-3 py-2 text-sm"
          placeholder={t.newTitle}
          aria-label={t.newTitle}
          value={title}
          maxLength={200}
          onChange={(e) => setTitle(e.target.value)}
        />
        {steps.map((step, index) => (
          <div key={index} className="flex flex-col gap-1 rounded-lg bg-surface-2 p-2">
            <input
              className="rounded-lg border border-line bg-surface px-3 py-1.5 text-sm"
              placeholder={`${t.stepTitle} ${index + 1}`}
              aria-label={`${t.stepTitle} ${index + 1}`}
              value={step.title}
              maxLength={200}
              onChange={(e) => setSteps((all) => all.map((s, i) => (i === index ? { ...s, title: e.target.value } : s)))}
            />
            <span className="text-xs text-ink-muted">{t.pickCards}</span>
            <div className="flex flex-wrap gap-1">
              {cards.length === 0 ? <span className="text-xs text-ink-faint">{t.needCards}</span> : null}
              {cards.map((card) => {
                const picked = step.cardIds.includes(card.id);
                return (
                  <button
                    key={card.id}
                    type="button"
                    aria-pressed={picked}
                    className={`rounded-full border px-2 py-0.5 text-xs ${picked ? "border-accent bg-accent/15 text-ink" : "border-line text-ink-muted"}`}
                    onClick={() =>
                      setSteps((all) =>
                        all.map((s, i) => (i === index ? { ...s, cardIds: picked ? s.cardIds.filter((id) => id !== card.id) : [...s.cardIds, card.id].slice(0, 20) } : s)),
                      )
                    }
                  >
                    {card.front.slice(0, 40)}
                  </button>
                );
              })}
            </div>
          </div>
        ))}
        <div className="flex gap-2">
          <Button size="sm" variant="secondary" disabled={steps.length >= 30} onClick={() => setSteps((all) => [...all, { title: "", cardIds: [] }])}>
            {t.addStep}
          </Button>
          <Button size="sm" disabled={busy || cards.length === 0} onClick={() => void create()}>
            {t.create}
          </Button>
        </div>
      </div>
    </Card>
  );
}
