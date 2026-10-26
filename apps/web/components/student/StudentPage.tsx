"use client";

import { useCallback, useEffect, useState } from "react";
import { BookOpen, Brain, Layers, ListTodo, Sparkles } from "lucide-react";
import { hasNextStudentPage, studentRequest } from "@/lib/student-api";
import { useI18n } from "@/lib/i18n/context";
import { PageFrame } from "../pages/PageFrame";
import { Comparison } from "./Comparison";
import { LearningPaths } from "./LearningPaths";

type Job = {
  parser_version: string;
  id: string;
  document_id: string;
  project_id: string | null;
  state: string;
  attempts: number;
  max_attempts: number;
  error_message: string | null;
};
type Entry = { title: string; job: Job };
type Section = { start: number; end: number; heading: string | null; page: number | null };
type Page = { text: string; offset: number; total_chars: number };
type Citation = { n: number; excerpt: string; location: string };
type Quiz = { question: string; choices: string[]; answer: number; explanation: string };
type Learning = {
  status: string;
  text: string;
  generated: boolean;
  provider: string | null;
  citations: Citation[];
  quiz: { items: Quiz[] } | null;
  /** Proposed cards (kind "flashcards"); nothing is stored until the owner saves one. */
  flashcards?: CardProposal[] | null;
};

/** A source-anchored card proposal; the exact body POST /student/cards accepts. */
interface CardProposal {
  document_id: string;
  revision_id: string;
  chunk_id: string;
  project_id: string | null;
  front: string;
  back: string;
  quote_start: number;
  quote_end: number;
}

/** GET /student/practice-plan: due cards from the real recall schedule, nothing generated. */
interface PracticePlan {
  items: { card_id: string; due_at: string; reason: string }[];
  empty_reason: string | null;
}

interface StudyCardOut {
  id: string;
  document_id: string;
  revision_id: string;
  chunk_id: string;
  project_id?: string | null;
  front: string;
  back: string;
  quote: string;
  due_at: string;
  version: number;
  interval_days: number;
}

interface StudyProgressOut {
  active_cards: number;
  due_cards: number;
  review_events: number;
  reviewed_cards: number;
  assessment: string;
}

interface ConceptNode {
  id: string;
  label: string;
  source: number;
  quote: string;
}

interface ConceptEdge {
  start: string;
  end: string;
  label: string;
  source: number;
  quote: string;
}

/** POST /student/synthesize (kind "concept_graph"); graph is null without enough evidence. */
interface SynthesisOut {
  status: string;
  generated: boolean;
  scope?: string;
  graph: { nodes: ConceptNode[]; edges: ConceptEdge[] } | null;
}

export function StudentPage() {
  const { m, f } = useI18n();
  const t = m.student;
  const [entries, setEntries] = useState<Entry[]>([]);
  const [libraryOffset, setLibraryOffset] = useState(0);
  const [moreBooks, setMoreBooks] = useState(false);
  const [selected, setSelected] = useState<Entry | null>(null);
  const [page, setPage] = useState<Page | null>(null);
  const [sections, setSections] = useState<Section[]>([]);
  const [sectionStart, setSectionStart] = useState<number | null>(null);
  const [question, setQuestion] = useState("");
  const [language, setLanguage] = useState("uz");
  const [answer, setAnswer] = useState<Learning | null>(null);
  const [choices, setChoices] = useState<Record<number, number>>({});
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [provider, setProvider] = useState(false);
  const [embedding, setEmbedding] = useState(false);
  const [indexOffset, setIndexOffset] = useState(0);
  const [indexNotice, setIndexNotice] = useState("");
  const [offset, setOffset] = useState(0);
  const [text, setText] = useState("");

  // Enhanced reader states
  const [activeTab, setActiveTab] = useState<"reader" | "plan" | "flashcards" | "concepts">("reader");
  const [fontSize, setFontSize] = useState<"sm" | "base" | "lg">("base");
  const [readerTheme, setReaderTheme] = useState<"default" | "sepia" | "contrast">("default");
  const [flippedCards, setFlippedCards] = useState<Record<string, boolean>>({});
  const [practicePlan, setPracticePlan] = useState<PracticePlan | null>(null);
  const [proposals, setProposals] = useState<CardProposal[]>([]);

  // Real backend study cards, progress and synthesis
  const [cards, setCards] = useState<StudyCardOut[]>([]);
  const [progress, setProgress] = useState<StudyProgressOut | null>(null);
  const [conceptGraph, setConceptGraph] = useState<SynthesisOut | null>(null);
  const [conceptLoading, setConceptLoading] = useState(false);

  const loadCards = useCallback(async () => {
    try {
      const [fetchedCards, fetchedProgress] = await Promise.all([
        studentRequest<StudyCardOut[]>("student/cards"),
        studentRequest<StudyProgressOut>("student/progress"),
      ]);
      setCards(fetchedCards);
      setProgress(fetchedProgress);
    } catch {
      // Offline or empty
    }
  }, []);

  useEffect(() => {
    if (activeTab !== "flashcards" && activeTab !== "plan") return;
    let active = true;
    Promise.all([
      studentRequest<StudyCardOut[]>("student/cards"),
      studentRequest<StudyProgressOut>("student/progress"),
      studentRequest<PracticePlan>("student/practice-plan"),
    ])
      .then(([fetchedCards, fetchedProgress, plan]) => {
        if (active) {
          setCards(fetchedCards);
          setProgress(fetchedProgress);
          setPracticePlan(plan);
        }
      })
      .catch((e) => {
        if (active) setError(String(e));
      });
    return () => {
      active = false;
    };
  }, [activeTab]);

  async function handleReview(card: StudyCardOut, rating: "again" | "hard" | "good" | "easy") {
    try {
      await studentRequest(`student/cards/${card.id}/review`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          event_id: crypto.randomUUID(),
          expected_version: card.version,
          rating,
        }),
      });
      await loadCards();
    } catch (e) {
      setError(String(e));
    }
  }

  async function proposeCards() {
    if (!selected) return;
    const result = await studentRequest<Learning>(`student/documents/${selected.job.document_id}/learn`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kind: "flashcards", question, language, section_start: sectionStart }),
    });
    setProposals(result.flashcards ?? []);
  }

  async function saveProposal(index: number) {
    await studentRequest("student/cards", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(proposals[index]),
    });
    setProposals((current) => current.filter((_, i) => i !== index));
    await loadCards();
  }

  async function handleDeleteCard(cardId: string) {
    try {
      await studentRequest(`student/cards/${cardId}?confirm=true`, { method: "DELETE" });
      await loadCards();
    } catch (e) {
      setError(String(e));
    }
  }

  async function handleGenerateConceptGraph() {
    if (!documentId) return;
    setConceptLoading(true);
    try {
      const res = await studentRequest<SynthesisOut>("student/synthesize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          document_ids: [documentId],
          question: m.student.concepts.question,
          language,
          kind: "concept_graph",
        }),
      });
      setConceptGraph(res);
    } catch (e) {
      setError(String(e));
    } finally {
      setConceptLoading(false);
    }
  }

  const refresh = useCallback(async () => {
    const rows = await studentRequest<Entry[]>(`student/library?offset=${libraryOffset}&limit=31`);
    setEntries(rows.slice(0, 30));
    setMoreBooks(rows.length > 30);
    setSelected((current) => (current ? rows.find((e) => e.job.id === current.job.id) ?? null : null));
  }, [libraryOffset]);

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        await refresh();
        const status = await studentRequest<{
          ai_provider_configured: boolean;
          embedding_provider_configured: boolean;
        }>("student/status");
        if (active) {
          setProvider(status.ai_provider_configured);
          setEmbedding(status.embedding_provider_configured);
        }
      } catch (e) {
        if (active) setError(String(e));
      }
    }
    void load();
    const timer = window.setInterval(() => {
      void refresh().catch((e) => setError(String(e)));
    }, 2000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [refresh]);

  const selectedId = selected?.job.id;
  const documentId = selected?.job.document_id;
  const state = selected?.job.state;

  useEffect(() => {
    if (!selectedId || !documentId || state !== "completed") return;
    let active = true;
    Promise.all([
      studentRequest<Page>(`student/readings/${selectedId}?offset=${offset}`),
      studentRequest<{ sections: Section[] }>(`student/documents/${documentId}/structure`),
    ])
      .then(([result, structure]) => {
        if (active) {
          setPage(result);
          setSections(structure.sections);
        }
      })
      .catch((e) => {
        if (active) setError(String(e));
      });
    return () => {
      active = false;
    };
  }, [selectedId, documentId, state, offset]);

  async function perform(action: () => Promise<void>) {
    setBusy(true);
    setError("");
    try {
      await action();
      await refresh();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  function choose(entry: Entry) {
    setSelected(entry);
    setOffset(0);
    setPage(null);
    setSections([]);
    setSectionStart(null);
    setAnswer(null);
    setChoices({});
    setIndexOffset(0);
    setIndexNotice("");
    setFlippedCards({});
    setProposals([]);
    setConceptGraph(null);
  }

  async function learn(kind: string) {
    if (!selected) return;
    const result = await studentRequest<Learning>(`student/documents/${selected.job.document_id}/learn`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kind, question, language, section_start: sectionStart }),
    });
    setAnswer(result);
    setChoices({});
  }

  const button = "rounded-lg border border-line px-3 py-2 text-sm disabled:opacity-40 transition-colors hover:bg-surface-2";

  const readPercent = page && page.total_chars > 0
    ? Math.min(100, Math.round(((page.offset + (page.text?.length || 0)) / page.total_chars) * 100))
    : 0;

  return (
    <PageFrame title={t.title} subtitle={t.subtitle}>
      <p className="mb-4 text-sm text-ink-muted">
        {t.limits} {t.ocrNeedsWorker}
      </p>
      {!provider && (
        <p role="status" className="mb-4 text-sm text-warning">
          {t.noProvider}
        </p>
      )}
      {error && (
        <p role="alert" className="mb-4 text-danger">
          {error}
        </p>
      )}

      {/* Upload and Text Intake */}
      <section aria-label={t.intake.region} className="mb-6 grid gap-3 rounded-2xl border border-line bg-surface p-4">
        <label className="grid gap-2 text-sm font-semibold text-ink">
          {t.intake.upload}
          <input
            type="file"
            accept=".pdf,.epub,.docx"
            disabled={busy}
            className="text-xs file:mr-3 file:rounded-lg file:border-0 file:bg-surface-2 file:px-3 file:py-1.5 file:text-xs file:font-semibold file:text-ink hover:file:bg-surface-3"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (!file) return;
              if (file.size > 5 * 1024 * 1024) {
                setError(t.fileTooLarge);
                return;
              }
              void perform(async () => {
                await studentRequest("student/uploads?filename=" + encodeURIComponent(file.name), {
                  method: "POST",
                  body: file,
                });
              });
            }}
          />
        </label>
        <label htmlFor="student-text" className="text-sm font-semibold text-ink">
          {t.intake.textLabel}
        </label>
        <textarea
          id="student-text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          maxLength={2000000}
          rows={3}
          placeholder={t.intake.textPlaceholder}
          className="rounded-lg border border-line bg-surface-2 p-3 text-sm text-ink placeholder:text-ink-faint focus:border-accent focus:outline-none"
        />
        <div>
          <button
            className={button}
            disabled={busy || !text.trim()}
            onClick={() =>
              void perform(async () => {
                await studentRequest("student/readings", {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({ text, title: "O‘quv matni" }),
                });
                setText("");
              })
            }
          >
            {t.intake.saveText}
          </button>
        </div>
      </section>

      <div className="grid gap-6 md:grid-cols-[240px_minmax(0,1fr)]">
        {/* Library sidebar */}
        <nav aria-label={t.library.region} className="grid content-start gap-2">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold text-ink">{t.library.heading}</h2>
            <span className="text-xs text-ink-faint">{f(t.library.count, { n: entries.length })}</span>
          </div>
          {!entries.length && <p className="text-sm text-ink-muted">{t.library.empty}</p>}
          {entries.map((entry) => (
            <button
              key={entry.job.id}
              className={`${button} break-words text-left ${
                entry.job.id === selectedId ? "border-accent bg-accent/10" : ""
              }`}
              aria-pressed={entry.job.id === selectedId}
              onClick={() => choose(entry)}
            >
              <div className="font-medium text-ink">{entry.title}</div>
              <span className="block text-xs text-ink-muted">
                {(t.jobState as Record<string, string>)[entry.job.state] ?? entry.job.state}
              </span>
            </button>
          ))}
          {entries.length > 0 && (
            <p aria-live="polite" className="text-xs text-ink-muted">
              {libraryOffset + 1}–{libraryOffset + entries.length}
            </p>
          )}
          <div className="flex flex-wrap gap-2 pt-2">
            <button
              className={button}
              disabled={libraryOffset === 0}
              onClick={() => setLibraryOffset(Math.max(0, libraryOffset - 30))}
            >
              {t.library.previous}
            </button>
            <button
              className={button}
              disabled={!moreBooks}
              onClick={() => setLibraryOffset(libraryOffset + 30)}
            >
              {t.library.next}
            </button>
          </div>
        </nav>

        {/* Main reading & study workspace */}
        <section className="min-w-0" aria-label={t.workspace.region}>
          {selected && (
            <>
              {/* Header */}
              <div className="mb-4 flex flex-wrap items-center justify-between gap-3 border-b border-line pb-3">
                <div>
                  <h2 className="text-lg font-bold text-ink">{selected.title}</h2>
                  <p role="status" className="text-xs text-ink-muted">
                    {f(t.workspace.attempts, { attempts: selected.job.attempts, max: selected.job.max_attempts })}
                  </p>
                </div>

                {/* Study Mode Navigation Tabs */}
                {selected.job.state === "completed" && (
                  <div className="flex items-center gap-1 rounded-xl border border-line bg-surface p-1 text-xs">
                    <button
                      className={`flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 font-medium transition-colors ${
                        activeTab === "reader" ? "bg-surface-2 text-ink" : "text-ink-muted hover:text-ink"
                      }`}
                      onClick={() => setActiveTab("reader")}
                    >
                      <BookOpen size={13} /> {t.tabs.reader}
                    </button>
                    <button
                      className={`flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 font-medium transition-colors ${
                        activeTab === "plan" ? "bg-surface-2 text-ink" : "text-ink-muted hover:text-ink"
                      }`}
                      onClick={() => setActiveTab("plan")}
                    >
                      <ListTodo size={13} /> {t.tabs.plan}
                    </button>
                    <button
                      className={`flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 font-medium transition-colors ${
                        activeTab === "flashcards" ? "bg-surface-2 text-ink" : "text-ink-muted hover:text-ink"
                      }`}
                      onClick={() => setActiveTab("flashcards")}
                    >
                      <Layers size={13} /> {t.tabs.flashcards}
                    </button>
                    <button
                      className={`flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 font-medium transition-colors ${
                        activeTab === "concepts" ? "bg-surface-2 text-ink" : "text-ink-muted hover:text-ink"
                      }`}
                      onClick={() => setActiveTab("concepts")}
                    >
                      <Brain size={13} /> {t.tabs.concepts}
                    </button>
                  </div>
                )}
              </div>

              {selected.job.error_message && (
                <p role="alert" className="mb-4 rounded-xl border border-danger/30 bg-danger/8 p-3 text-sm text-danger">
                  {selected.job.error_message}
                </p>
              )}

              {["queued", "running"].includes(selected.job.state) && (
                <button
                  disabled={busy}
                  className={button}
                  onClick={() =>
                    void perform(async () => {
                      await studentRequest(`knowledge/document-jobs/${selected.job.id}/cancel`, { method: "POST" });
                    })
                  }
                >
                  {t.workspace.cancel}
                </button>
              )}

              {selected.job.parser_version === "isolated-extraction/v1" &&
                ["failed", "cancelled"].includes(selected.job.state) && (
                  <button
                    disabled={busy}
                    className={button}
                    onClick={() =>
                      void perform(async () => {
                        const job = await studentRequest<Job>(`student/readings/${selected.job.id}/retry`, {
                          method: "POST",
                        });
                        choose({ ...selected, job });
                      })
                    }
                  >
                    {t.workspace.retry}
                  </button>
                )}

              {selected.job.state === "completed" && (
                <>
                  {/* TAB 1: Professional Book Reader & Learn Mode */}
                  {activeTab === "reader" && (
                    <div className="space-y-4">
                      {/* Reading Controls Bar */}
                      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-line bg-surface p-2.5 text-xs">
                        <div className="flex items-center gap-2">
                          <span className="text-ink-muted">{t.reader.font}</span>
                          {(["sm", "base", "lg"] as const).map((sz) => (
                            <button
                              key={sz}
                              className={`rounded px-2 py-0.5 font-mono ${
                                fontSize === sz ? "bg-accent/20 text-accent font-bold" : "text-ink-faint hover:text-ink"
                              }`}
                              onClick={() => setFontSize(sz)}
                            >
                              {sz.toUpperCase()}
                            </button>
                          ))}
                        </div>

                        <div className="flex items-center gap-2">
                          <span className="text-ink-muted">{t.reader.theme}</span>
                          <button
                            className={`rounded px-2 py-0.5 ${
                              readerTheme === "default" ? "bg-surface-2 text-ink font-semibold" : "text-ink-faint"
                            }`}
                            onClick={() => setReaderTheme("default")}
                          >
                            {t.reader.themeDefault}
                          </button>
                          <button
                            className={`rounded px-2 py-0.5 ${
                              readerTheme === "sepia" ? "bg-[#fbf0d9] text-[#5f4b32] font-semibold" : "text-ink-faint"
                            }`}
                            onClick={() => setReaderTheme("sepia")}
                          >
                            {t.reader.themeSepia}
                          </button>
                          <button
                            className={`rounded px-2 py-0.5 ${
                              readerTheme === "contrast" ? "bg-black text-white font-semibold" : "text-ink-faint"
                            }`}
                            onClick={() => setReaderTheme("contrast")}
                          >
                            {t.reader.themeContrast}
                          </button>
                        </div>

                        {/* Progress Gauge */}
                        <div className="flex items-center gap-2">
                          <span className="text-ink-muted">{f(t.reader.readPercent, { percent: readPercent })}</span>
                          <div className="h-1.5 w-16 overflow-hidden rounded-full bg-surface-2">
                            <div className="h-full bg-accent" style={{ width: `${readPercent}%` }} />
                          </div>
                        </div>
                      </div>

                      {/* Section Dropdown */}
                      <label className="block">
                        <span className="mb-1 block text-xs font-semibold text-ink-muted">{t.reader.sectionLabel}</span>
                        <select
                          className="block w-full rounded-lg border border-line bg-surface p-2.5 text-sm text-ink focus:border-accent focus:outline-none"
                          value={sectionStart ?? ""}
                          onChange={(e) => {
                            const start = e.target.value === "" ? null : Number(e.target.value);
                            setSectionStart(start);
                            setOffset(start ?? 0);
                          }}
                        >
                          <option value="">{t.reader.fromStart}</option>
                          {sections.map((section, i) => (
                            <option key={section.start} value={section.start}>
                              {section.heading ??
                                (section.page
                                  ? f(t.reader.pageOption, { page: section.page })
                                  : f(t.reader.sectionOption, { n: i + 1 }))}
                            </option>
                          ))}
                        </select>
                      </label>

                      {/* Article Text View */}
                      <article
                        aria-label={t.reader.article}
                        className={`whitespace-pre-wrap break-words rounded-xl border border-line p-5 leading-relaxed shadow-sm transition-all ${
                          fontSize === "sm" ? "text-xs" : fontSize === "lg" ? "text-base" : "text-sm"
                        } ${
                          readerTheme === "sepia"
                            ? "bg-[#faf4e6] text-[#42331f]"
                            : readerTheme === "contrast"
                            ? "bg-black text-zinc-100"
                            : "bg-surface text-ink"
                        }`}
                      >
                        {page?.text}
                      </article>

                      {/* Pagination Controls */}
                      <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
                        <div className="flex items-center gap-2">
                          <button
                            className={button}
                            disabled={offset === 0}
                            onClick={() => setOffset(Math.max(0, offset - 4000))}
                          >
                            {t.reader.previous}
                          </button>
                          <span className="text-xs text-ink-muted">
                            {f(t.reader.chars, { offset: page?.offset ?? 0, total: page?.total_chars ?? 0 })}
                          </span>
                          <button
                            className={button}
                            disabled={!page || !hasNextStudentPage(page)}
                            onClick={() => setOffset(offset + 4000)}
                          >
                            {t.reader.next}
                          </button>
                        </div>

                        {embedding && (
                          <button
                            className={button}
                            disabled={busy}
                            onClick={() =>
                              void perform(async () => {
                                let next = indexOffset;
                                for (let batch = 0; batch < 100; batch++) {
                                  const result = await studentRequest<{ indexed: number; next_offset: number | null }>(
                                    `student/documents/${selected.job.document_id}/semantic-index?offset=${next}`,
                                    { method: "POST" }
                                  );
                                  setIndexNotice(f(t.reader.indexed, { n: next + result.indexed }));
                                  if (result.next_offset === null) {
                                    setIndexOffset(0);
                                    return;
                                  }
                                  if (result.next_offset <= next) throw new Error(t.indexMismatch);
                                  next = result.next_offset;
                                  setIndexOffset(next);
                                }
                              })
                            }
                          >
                            {t.reader.buildIndex}
                          </button>
                        )}
                      </div>

                      {indexNotice && <p role="status" className="text-xs text-accent">{indexNotice}</p>}

                      {/* AI Learning & Source-Linked Chat */}
                      <div className="mt-6 rounded-2xl border border-line bg-surface p-4">
                        <div className="flex flex-wrap items-center justify-between gap-3">
                          <h3 className="flex items-center gap-2 font-semibold text-ink">
                            <Sparkles size={16} className="text-accent" />
                            {t.learn.heading}
                          </h3>
                          <label className="flex items-center gap-1.5 text-xs text-ink-muted">
                            {t.learn.answerLanguage}
                            <select
                              value={language}
                              onChange={(e) => setLanguage(e.target.value)}
                              className="rounded border border-line bg-surface-2 p-1 text-xs text-ink"
                            >
                              <option value="uz">{t.learn.languages.uz}</option>
                              <option value="en">{t.learn.languages.en}</option>
                              <option value="ru">{t.learn.languages.ru}</option>
                            </select>
                          </label>
                        </div>

                        <label htmlFor="student-question" className="mt-3 block text-xs font-semibold text-ink-muted">
                          {t.learn.questionLabel}
                        </label>
                        <input
                          id="student-question"
                          className="my-2 w-full rounded-lg border border-line bg-surface-2 p-3 text-sm text-ink placeholder:text-ink-faint focus:border-accent focus:outline-none"
                          placeholder={t.learn.questionPlaceholder}
                          value={question}
                          onChange={(e) => setQuestion(e.target.value)}
                          maxLength={2000}
                        />

                        <div className="flex flex-wrap gap-2">
                          {[
                            ["answer", t.learn.answer],
                            ["summary", t.learn.summary],
                            ["study_guide", t.learn.studyGuide],
                            ["quiz", t.learn.quiz],
                          ].map(([kind, label]) => (
                            <button
                              className={button}
                              key={kind}
                              disabled={busy || !provider || (kind === "answer" && !question.trim())}
                              onClick={() => void perform(() => learn(kind))}
                            >
                              {label}
                            </button>
                          ))}
                        </div>

                        {answer && (
                          <div aria-live="polite" className="mt-5 grid gap-3 border-t border-line pt-4">
                            <p className="text-xs text-ink-muted">
                              {answer.generated
                                ? f(t.learn.generatedNote, { provider: String(answer.provider) })
                                : t.learn.noEvidence}
                            </p>
                            {!answer.quiz && (
                              <p className="whitespace-pre-wrap break-words text-sm leading-relaxed text-ink">
                                {answer.text}
                              </p>
                            )}

                            {/* Quiz Items */}
                            {answer.quiz?.items.map((item, i) => (
                              <fieldset key={i} className="rounded-xl border border-line bg-surface-2/50 p-4">
                                <legend className="font-semibold text-ink">{item.question}</legend>
                                {item.choices.map((choice, j) => (
                                  <label key={j} className="my-2.5 flex cursor-pointer items-center gap-2 text-sm text-ink">
                                    <input
                                      type="radio"
                                      name={`quiz-${i}`}
                                      checked={choices[i] === j}
                                      onChange={() => setChoices({ ...choices, [i]: j })}
                                    />
                                    {choice}
                                  </label>
                                ))}
                                {choices[i] !== undefined && (
                                  <p
                                    role="status"
                                    className={`mt-2 text-xs font-semibold ${
                                      choices[i] === item.answer ? "text-success" : "text-warning"
                                    }`}
                                  >
                                    {choices[i] === item.answer ? t.learn.correct : t.learn.incorrect}{" "}
                                    <span className="font-normal text-ink-muted">{item.explanation}</span>
                                  </p>
                                )}
                              </fieldset>
                            ))}

                            {/* Exact Citations */}
                            <h3 className="mt-2 font-semibold text-ink">{t.learn.sources}</h3>
                            {answer.citations.map((citation) => (
                              <blockquote
                                className="cursor-pointer rounded-r-lg border-l-2 border-accent bg-surface-2/40 p-3 text-xs leading-relaxed transition-colors hover:bg-surface-2"
                                key={citation.n}
                                onClick={() => {
                                  // Jump towards excerpt if location matches
                                }}
                              >
                                <span className="font-semibold text-accent">[{citation.n}] {citation.location}</span>
                                <p className="mt-1 text-ink-muted italic">&ldquo;{citation.excerpt}&rdquo;</p>
                              </blockquote>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  )}

                  {/* TAB 2: Due-recall plan from the real review schedule (GET /student/practice-plan) */}
                  {activeTab === "plan" && (
                    <div className="space-y-4 rounded-2xl border border-line bg-surface p-5">
                      <div>
                        <h3 className="font-bold text-ink">{t.plan.heading}</h3>
                        <p className="text-xs text-ink-muted">
                          {t.plan.hint}
                        </p>
                      </div>
                      {!practicePlan ? (
                        <p className="text-xs text-ink-muted">{t.plan.loading}</p>
                      ) : practicePlan.items.length === 0 ? (
                        <p className="rounded-xl border border-dashed border-line p-4 text-center text-xs text-ink-muted">
                          {cards.length === 0
                            ? t.plan.noCards
                            : t.plan.nothingDue}
                        </p>
                      ) : (
                        <ol className="grid gap-2">
                          {practicePlan.items.map((item) => {
                            const card = cards.find((c) => c.id === item.card_id);
                            return (
                              <li key={item.card_id} className="rounded-xl border border-line bg-surface-2/40 p-3 text-sm">
                                <span className="font-semibold text-ink">{card?.front ?? t.plan.card}</span>
                                <span className="ml-2 text-xs text-ink-muted">
                                  {item.reason === "scheduled_recall" ? t.plan.scheduledRecall : t.plan.firstRecall} ·{" "}
                                  {new Date(item.due_at).toLocaleString()}
                                </span>
                              </li>
                            );
                          })}
                        </ol>
                      )}
                    </div>
                  )}
                  {activeTab === "plan" && (
                    <LearningPaths
                      cards={cards.map((c) => ({ id: c.id, front: c.front }))}
                      projectId={selected?.job.project_id ?? null}
                    />
                  )}

                  {/* TAB 3: Interactive Flashcards */}
                  {activeTab === "flashcards" && (
                    <div className="space-y-4 rounded-2xl border border-line bg-surface p-5">
                      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                        <div>
                          <h3 className="font-bold text-ink">{t.flashcards.heading}</h3>
                          <p className="text-xs text-ink-muted">
                            {t.flashcards.hint}
                          </p>
                        </div>
                        {progress && (
                          <div className="flex items-center gap-2 text-xs">
                            <span className="rounded-full bg-accent/10 px-2.5 py-1 font-medium text-accent border border-accent/20">
                              {f(t.flashcards.active, { n: progress.active_cards })}
                            </span>
                            <span className="rounded-full bg-success/12 px-2.5 py-1 font-medium text-success border border-success/30">
                              {f(t.flashcards.reviewed, { n: progress.reviewed_cards })}
                            </span>
                          </div>
                        )}
                      </div>

                      {cards.length > 0 ? (
                        <div className="grid gap-4 sm:grid-cols-2">
                          {cards.map((card) => {
                            const isFlipped = !!flippedCards[card.id];
                            return (
                              <div
                                key={card.id}
                                className="rounded-2xl border border-line bg-surface-2/40 p-4 shadow-sm transition-all hover:border-accent flex flex-col justify-between gap-3"
                              >
                                <div
                                  className="cursor-pointer"
                                  onClick={() =>
                                    setFlippedCards({
                                      ...flippedCards,
                                      [card.id]: !isFlipped,
                                    })
                                  }
                                >
                                  <div className="flex items-center justify-between text-xs text-ink-faint">
                                    <span className="font-mono">{f(t.flashcards.version, { version: card.version })}</span>
                                    <span className="text-[11px] font-medium text-accent">
                                      {isFlipped ? t.flashcards.back : t.flashcards.front}
                                    </span>
                                  </div>
                                  <div className="my-3 min-h-[60px] flex items-center justify-center text-center">
                                    {!isFlipped ? (
                                      <h4 className="text-base font-bold text-ink">{card.front}</h4>
                                    ) : (
                                      <p className="text-xs leading-relaxed text-ink-muted">{card.back}</p>
                                    )}
                                  </div>
                                  {card.quote && (
                                    <p className="text-[11px] text-ink-faint italic border-t border-line/40 pt-2 line-clamp-2">
                                      &ldquo;{card.quote}&rdquo;
                                    </p>
                                  )}
                                </div>

                                <div className="flex items-center justify-between border-t border-line/60 pt-2 text-xs">
                                  <button
                                    type="button"
                                    onClick={() => void handleDeleteCard(card.id)}
                                    className="text-[11px] text-danger hover:underline"
                                  >
                                    {t.flashcards.delete}
                                  </button>
                                  <div className="flex items-center gap-1.5">
                                    <button
                                      type="button"
                                      className="px-2 py-0.5 rounded bg-surface-3 hover:bg-surface-2 text-[11px] text-ink font-medium"
                                      onClick={() => void handleReview(card, "again")}
                                    >
                                      {t.flashcards.again}
                                    </button>
                                    <button
                                      type="button"
                                      className="px-2 py-0.5 rounded bg-surface-3 hover:bg-surface-2 text-[11px] text-warning font-medium"
                                      onClick={() => void handleReview(card, "hard")}
                                    >
                                      {t.flashcards.hard}
                                    </button>
                                    <button
                                      type="button"
                                      className="px-2 py-0.5 rounded bg-surface-3 hover:bg-surface-2 text-[11px] text-primary font-medium"
                                      onClick={() => void handleReview(card, "good")}
                                    >
                                      {t.flashcards.good}
                                    </button>
                                    <button
                                      type="button"
                                      className="px-2 py-0.5 rounded bg-surface-3 hover:bg-surface-2 text-[11px] text-success font-medium"
                                      onClick={() => void handleReview(card, "easy")}
                                    >
                                      {t.flashcards.easy}
                                    </button>
                                  </div>
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      ) : (
                        <p className="rounded-xl border border-dashed border-line p-6 text-center text-xs text-ink-muted">
                          {t.flashcards.empty}
                        </p>
                      )}

                      <div className="space-y-3 border-t border-line pt-4">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <p className="text-xs text-ink-muted">
                            {t.flashcards.proposeHint}
                          </p>
                          <button
                            type="button"
                            className={button}
                            disabled={busy || !provider}
                            onClick={() => void perform(proposeCards)}
                          >
                            {t.flashcards.propose}
                          </button>
                        </div>
                        {proposals.map((proposal, index) => (
                          <div key={`${proposal.chunk_id}-${proposal.quote_start}`} className="rounded-xl border border-line bg-surface-2/40 p-3 text-sm">
                            <p className="font-semibold text-ink">{proposal.front}</p>
                            <p className="mt-1 text-xs text-ink-muted">{proposal.back}</p>
                            <button type="button" className={`${button} mt-2`} onClick={() => void perform(() => saveProposal(index))}>
                              {t.flashcards.save}
                            </button>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* TAB 4: Concept Visualization Tree */}
                  {activeTab === "concepts" && (
                    <div className="space-y-4 rounded-2xl border border-line bg-surface p-5">
                      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                        <div>
                          <h3 className="font-bold text-ink">{t.concepts.heading}</h3>
                          <p className="text-xs text-ink-muted">{t.concepts.hint}</p>
                        </div>
                        <button
                          type="button"
                          className={button}
                          disabled={conceptLoading || !provider}
                          onClick={() => void handleGenerateConceptGraph()}
                        >
                          {conceptLoading ? t.concepts.analyzing : t.concepts.analyze}
                        </button>
                      </div>

                      {conceptGraph && !conceptGraph.graph && (
                        <p role="status" className="rounded-xl border border-line p-3 text-xs text-ink-muted">
                          {t.concepts.noEvidence}
                        </p>
                      )}
                      {conceptGraph?.graph && (
                        <div className="rounded-xl border border-primary/20 bg-primary/5 p-4 space-y-3">
                          <div className="flex items-center justify-between text-xs">
                            <span className="font-semibold text-primary">{t.concepts.graphTitle}</span>
                            <span className="text-ink-faint">{t.concepts.graphNote}</span>
                          </div>
                          <div className="grid gap-2 sm:grid-cols-2">
                            {conceptGraph.graph.nodes.map((n) => (
                              <div key={n.id} className="p-2.5 rounded-lg border border-line bg-surface text-xs space-y-1">
                                <span className="font-bold text-ink">{n.label}</span>
                                <p className="text-ink-muted italic">&ldquo;{n.quote}&rdquo;</p>
                              </div>
                            ))}
                          </div>
                          {conceptGraph.graph.edges.length > 0 && (
                            <div className="pt-2 border-t border-line/60">
                              <h5 className="text-xs font-semibold text-ink mb-1.5">{t.concepts.edges}</h5>
                              <ul className="text-xs space-y-1 text-ink-muted">
                                {conceptGraph.graph.edges.map((e, i) => {
                                  const label = (id: string) =>
                                    conceptGraph.graph?.nodes.find((n) => n.id === id)?.label ?? id;
                                  return (
                                    <li key={i}>
                                      <strong>{label(e.start)}</strong> &rarr; <em>{e.label}</em> &rarr;{" "}
                                      <strong>{label(e.end)}</strong>
                                    </li>
                                  );
                                })}
                              </ul>
                            </div>
                          )}
                        </div>
                      )}

                      <div className="space-y-3 pt-2">
                        {sections.length > 0 ? (
                          sections.map((sec, idx) => (
                            <div key={idx} className="flex items-start gap-3 rounded-xl border border-line bg-surface-2/30 p-3">
                              <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-accent/15 text-xs font-bold text-accent">
                                {idx + 1}
                              </div>
                              <div className="flex-1">
                                <h4 className="text-sm font-semibold text-ink">
                                  {sec.heading || f(t.concepts.section, { n: idx + 1 })}
                                </h4>
                                <p className="text-xs text-ink-muted">
                                  {f(t.concepts.range, { start: sec.start, end: sec.end })}{" "}
                                  {sec.page ? f(t.concepts.pageNote, { page: sec.page }) : ""}
                                </p>
                              </div>
                              <button
                                className={button}
                                onClick={() => {
                                  setSectionStart(sec.start);
                                  setOffset(sec.start);
                                  setActiveTab("reader");
                                }}
                              >
                                {t.concepts.openReader}
                              </button>
                            </div>
                          ))
                        ) : (
                          <div className="rounded-xl border border-line bg-surface-2/20 p-4 text-center text-xs text-ink-muted">
                            {t.concepts.noSections}
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                  {activeTab === "concepts" && (
                    <Comparison
                      documents={entries.filter((e) => e.job.state === "completed").map((e) => ({ id: e.job.document_id, title: e.title }))}
                      projectId={selected?.job.project_id ?? null}
                      provider={provider}
                    />
                  )}
                </>
              )}
            </>
          )}
        </section>
      </div>
    </PageFrame>
  );
}
