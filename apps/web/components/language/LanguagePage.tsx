"use client";

import type { LanguageSession } from "@ezo/shared";
import { Badge, Card, Spinner } from "@ezo/ui";
import { FileText, MessageSquare, Trash2 } from "lucide-react";
import Link from "next/link";
import { useCallback } from "react";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n/context";
import { useApiData } from "@/lib/use-api-data";
import { PageFrame } from "../pages/PageFrame";

/** Format an estimated band range ("6", "5.5–6.5") or null when not assessed. */
export function bandText(low: number | null, high: number | null): string | null {
  if (low === null || high === null) return null;
  return low === high ? `${low}` : `${low}–${high}`;
}

export function LanguagePage() {
  const { m, f } = useI18n();
  const t = m.language;
  const fetchProgress = useCallback(() => api.languageProgress(), []);
  const { data: progress, error, reload } = useApiData(fetchProgress);
  const fetchSessions = useCallback(() => api.listLanguageSessions(), []);
  const { data: sessions, reload: reloadSessions } = useApiData(fetchSessions);
  const fetchVocabulary = useCallback(() => api.listVocabulary(), []);
  const { data: vocabulary } = useApiData(fetchVocabulary);

  async function remove(session: LanguageSession) {
    if (!window.confirm(t.confirmDelete)) return;
    await api.deleteLanguageSession(session.id);
    reload();
    reloadSessions();
  }

  const criteriaNames: Record<string, string> = {
    fluency_coherence: t.criteria.fluency,
    lexical_resource: t.criteria.lexical,
    grammatical_range_accuracy: t.criteria.grammar,
  };

  return (
    <PageFrame title={t.title} subtitle={t.subtitle}>
      <p className="mb-4 text-xs text-ink-faint" data-testid="language-disclaimer">
        {t.disclaimer}
      </p>
      {error ? (
        <p className="text-sm text-danger">{error.message}</p>
      ) : !progress || !sessions ? (
        <Spinner label={m.common.loading} />
      ) : (
        <div className="flex flex-col gap-4">
          <Card className="p-4" data-testid="language-goal">
            <h2 className="mb-1 text-sm font-medium">{t.goal}</h2>
            {progress.goals.length ? (
              progress.goals.map((goal) => (
                <p key={goal.id} className="text-sm text-ink-muted">
                  {goal.description}
                  {goal.target_band ? <Badge className="ml-2">IELTS {goal.target_band}</Badge> : null}
                  {goal.cefr_target ? <Badge className="ml-2">{goal.cefr_target}</Badge> : null}
                </p>
              ))
            ) : (
              <p className="text-sm text-ink-muted">{t.noGoal}</p>
            )}
          </Card>

          {Object.keys(progress.criteria_trend).length ? (
            <Card className="p-4" data-testid="language-trend">
              <h2 className="mb-2 text-sm font-medium">
                {t.trend} <span className="font-normal text-ink-faint">({t.trendNote})</span>
              </h2>
              <ul className="grid gap-1 text-sm sm:grid-cols-3">
                {Object.entries(progress.criteria_trend).map(([name, value]) => (
                  <li key={name}>
                    {criteriaNames[name] ?? name}: {value.older} → <strong>{value.newer}</strong>
                  </li>
                ))}
              </ul>
            </Card>
          ) : null}

          {progress.recurring_mistakes.length ? (
            <Card className="p-4" data-testid="language-mistakes">
              <h2 className="mb-2 text-sm font-medium">{t.mistakes}</h2>
              <ul className="flex flex-col gap-1 text-sm">
                {progress.recurring_mistakes.map((mistake) => (
                  <li key={mistake.category}>
                    <span className="font-medium">{mistake.category.replaceAll("_", " ")}</span>{" "}
                    <span className="text-ink-faint">×{mistake.count}</span>
                    <span className="block text-xs text-ink-muted">{mistake.example}</span>
                  </li>
                ))}
              </ul>
            </Card>
          ) : null}

          <section>
            <h2 className="mb-2 text-sm font-medium">
              {t.sessions}
              {progress.speaking_minutes ? (
                <span className="ml-2 font-normal text-ink-faint">{f(t.minutes, { n: progress.speaking_minutes })}</span>
              ) : null}
            </h2>
            {sessions.length === 0 ? (
              <p className="py-6 text-center text-sm text-ink-muted">{t.empty}</p>
            ) : (
              <ul className="flex flex-col gap-2" data-testid="language-sessions">
                {sessions.map((session) => (
                  <SessionRow key={session.id} session={session} onDelete={() => void remove(session)} />
                ))}
              </ul>
            )}
          </section>

          {vocabulary && vocabulary.length ? (
            <Card className="p-4" data-testid="language-vocabulary">
              <h2 className="mb-2 text-sm font-medium">{t.vocabulary}</h2>
              <ul className="grid gap-1 text-sm sm:grid-cols-2">
                {vocabulary.slice(0, 20).map((item) => (
                  <li key={item.term}>
                    <strong>{item.term}</strong> <span className="text-ink-muted">— {item.meaning}</span>
                  </li>
                ))}
              </ul>
            </Card>
          ) : null}
        </div>
      )}
    </PageFrame>
  );
}

function SessionRow({ session, onDelete }: { session: LanguageSession; onDelete: () => void }) {
  const { m, f } = useI18n();
  const t = m.language;
  const band = bandText(session.band_low, session.band_high);
  const mode = t.modes[session.mode as keyof typeof t.modes] ?? session.mode;
  const scores = [
    [t.criteria.fluency, session.fluency_score],
    [t.criteria.lexical, session.lexical_score],
    [t.criteria.grammar, session.grammar_score],
  ].filter((entry): entry is [string, number] => entry[1] !== null);

  return (
    <li className="rounded-xl border border-line bg-surface px-3 py-2" data-testid="language-session">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium">{mode}</span>
        <span className="text-xs text-ink-faint">{new Date(session.started_at).toLocaleDateString()}</span>
        {session.status === "active" ? <Badge>{t.active}</Badge> : null}
        {session.status === "abandoned" ? <Badge>{t.abandoned}</Badge> : null}
        {session.status === "completed" ? (
          <span className="text-xs" data-testid="language-band">
            {t.band}: <strong>{band ?? t.noBand}</strong>
          </span>
        ) : null}
        <span className="ml-auto flex items-center gap-1">
          {session.report_artifact_id ? (
            <Link
              href={`/artifacts?open=${session.report_artifact_id}`}
              className="rounded p-1.5 text-ink-faint hover:text-ink"
              aria-label={t.report}
              title={t.report}
            >
              <FileText size={15} />
            </Link>
          ) : null}
          {session.conversation_id ? (
            <Link
              href={`/chat/${session.conversation_id}`}
              className="rounded p-1.5 text-ink-faint hover:text-ink"
              aria-label={t.open}
              title={t.open}
            >
              <MessageSquare size={15} />
            </Link>
          ) : null}
          <button
            type="button"
            onClick={onDelete}
            className="rounded p-1.5 text-ink-faint hover:text-danger"
            aria-label={t.delete}
            title={t.delete}
          >
            <Trash2 size={15} />
          </button>
        </span>
      </div>
      {scores.length || session.user_words ? (
        <p className="mt-1 text-xs text-ink-muted">
          {scores.map(([name, value]) => `${name} ${value}`).join(" · ")}
          {session.pronunciation_score !== null
            ? ` · ${t.criteria.pronunciation} ${session.pronunciation_score} (${t.pronunciationNote})`
            : ""}
          {scores.length ? " · " : ""}
          {f(t.words, { n: session.user_words })}
        </p>
      ) : null}
    </li>
  );
}
