"use client";

import { Button, Card } from "@ezo/ui";
import { useState } from "react";
import { useI18n } from "@/lib/i18n/context";
import { studentRequest } from "@/lib/student-api";

/** POST /student/synthesize (kind "comparison"): a cited comparison of 2–4 documents. */
interface ComparisonOut {
  status: string;
  generated: boolean;
  text: string;
  citations: { n: number; excerpt: string; location: string; document_id?: string }[];
  provider: string | null;
}

interface DocumentOption {
  id: string;
  title: string;
}

export function Comparison({ documents, projectId, provider }: { documents: DocumentOption[]; projectId: string | null; provider: boolean }) {
  const { m, language } = useI18n();
  const t = m.studentExtras.comparison;
  const [picked, setPicked] = useState<string[]>([]);
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<ComparisonOut | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const toggle = (id: string) =>
    setPicked((all) => (all.includes(id) ? all.filter((x) => x !== id) : all.length >= 4 ? all : [...all, id]));

  const run = async () => {
    if (picked.length < 2) return setError(t.needTwo);
    if (!question.trim()) return;
    setBusy(true);
    setError("");
    setResult(null);
    try {
      const out = await studentRequest<ComparisonOut>("student/synthesize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ document_ids: picked, project_id: projectId, question: question.trim(), language, kind: "comparison" }),
      });
      setResult(out);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card className="flex flex-col gap-3 p-5" data-testid="comparison">
      <div>
        <h3 className="font-semibold text-ink">{t.title}</h3>
        <p className="mt-0.5 text-xs text-ink-muted">{t.note}</p>
      </div>
      {!provider ? <p className="text-xs text-warning">{t.offline}</p> : null}
      <span className="text-xs text-ink-muted">{t.pick}</span>
      <div className="flex flex-wrap gap-1">
        {documents.map((doc) => {
          const on = picked.includes(doc.id);
          return (
            <button
              key={doc.id}
              type="button"
              aria-pressed={on}
              className={`rounded-full border px-2 py-0.5 text-xs ${on ? "border-accent bg-accent/15 text-ink" : "border-line text-ink-muted"}`}
              onClick={() => toggle(doc.id)}
            >
              {doc.title.slice(0, 40)}
            </button>
          );
        })}
      </div>
      <div className="flex gap-2">
        <input
          className="flex-1 rounded-lg border border-line bg-surface px-3 py-2 text-sm"
          placeholder={t.placeholder}
          aria-label={t.question}
          value={question}
          maxLength={2000}
          onChange={(e) => setQuestion(e.target.value)}
        />
        <Button size="sm" disabled={busy || !provider} onClick={() => void run()}>
          {busy ? t.running : t.run}
        </Button>
      </div>
      {error ? <p className="text-sm text-danger" role="alert">{error}</p> : null}
      {result ? (
        <div className="rounded-xl border border-line bg-surface-2 p-3 text-sm" data-testid="comparison-result">
          {result.status === "insufficient_evidence" ? (
            <p className="text-ink-muted">{t.insufficient}</p>
          ) : (
            <>
              <p className="whitespace-pre-wrap text-ink">{result.text}</p>
              {result.citations.length ? (
                <>
                  <h4 className="mt-3 text-xs font-medium uppercase tracking-wide text-ink-muted">{t.sources}</h4>
                  <ol className="mt-1 flex flex-col gap-1 text-xs text-ink-muted">
                    {result.citations.map((c) => (
                      <li key={c.n}>
                        [{c.n}] {c.location}: “{c.excerpt.slice(0, 160)}”
                      </li>
                    ))}
                  </ol>
                </>
              ) : null}
            </>
          )}
        </div>
      ) : null}
    </Card>
  );
}
