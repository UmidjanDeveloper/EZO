"use client";

import { useCallback, useEffect, useState } from "react";
import { BookOpen, Brain, Layers, ListTodo, Sparkles } from "lucide-react";
import { hasNextStudentPage, studentRequest } from "@/lib/student-api";
import { PageFrame } from "../pages/PageFrame";

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
          question: "Hujjatdagi asosiy tushunchalar va ularning mantiqiy bog‘liqligi",
          language: "uz",
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
    <PageFrame title="EZO Student" subtitle="Manbani o‘qing, dalil bilan o‘rganing.">
      <p className="mb-4 text-sm text-ink-muted">
        PDF, EPUB, DOCX: 5 MiB gacha. Alohida xavfsiz worker talab qilinadi. Skanerlangan PDF uchun OCR hozircha mavjud emas.
      </p>
      {!provider && (
        <p role="status" className="mb-4 text-sm text-amber-600 dark:text-amber-400">
          AI provayder ulanmagan. O‘qish ishlaydi; AI javoblari, qo‘llanma va testlar uchun provayder kerak.
        </p>
      )}
      {error && (
        <p role="alert" className="mb-4 text-red-600">
          {error}
        </p>
      )}

      {/* Upload and Text Intake */}
      <section aria-label="Hujjat yuklash" className="mb-6 grid gap-3 rounded-2xl border border-line bg-surface p-4">
        <label className="grid gap-2 text-sm font-semibold text-ink">
          Hujjat yuklash
          <input
            type="file"
            accept=".pdf,.epub,.docx"
            disabled={busy}
            className="text-xs file:mr-3 file:rounded-lg file:border-0 file:bg-surface-2 file:px-3 file:py-1.5 file:text-xs file:font-semibold file:text-ink hover:file:bg-surface-3"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (!file) return;
              if (file.size > 5 * 1024 * 1024) {
                setError("Fayl 5 MiB dan katta.");
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
          Yoki o‘rganish uchun matn
        </label>
        <textarea
          id="student-text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          maxLength={2000000}
          rows={3}
          placeholder="O'rganmoqchi bo'lgan matningizni kiriting..."
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
            Matnni saqlash
          </button>
        </div>
      </section>

      <div className="grid gap-6 md:grid-cols-[240px_minmax(0,1fr)]">
        {/* Library sidebar */}
        <nav aria-label="Hujjatlar kutubxonasi" className="grid content-start gap-2">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold text-ink">Kutubxona</h2>
            <span className="text-xs text-ink-faint">{entries.length} manba</span>
          </div>
          {!entries.length && <p className="text-sm text-ink-muted">Hali hujjat yo‘q.</p>}
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
                {({
                  queued: "Navbatda",
                  running: "O‘qilmoqda",
                  completed: "Tayyor",
                  failed: "Xato",
                  cancelled: "Bekor qilindi",
                })[entry.job.state] ?? entry.job.state}
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
              Oldingi hujjatlar
            </button>
            <button
              className={button}
              disabled={!moreBooks}
              onClick={() => setLibraryOffset(libraryOffset + 30)}
            >
              Keyingi hujjatlar
            </button>
          </div>
        </nav>

        {/* Main reading & study workspace */}
        <section className="min-w-0" aria-label="O‘qish va o‘rganish">
          {selected && (
            <>
              {/* Header */}
              <div className="mb-4 flex flex-wrap items-center justify-between gap-3 border-b border-line pb-3">
                <div>
                  <h2 className="text-lg font-bold text-ink">{selected.title}</h2>
                  <p role="status" className="text-xs text-ink-muted">
                    Urinishlar: {selected.job.attempts}/{selected.job.max_attempts}
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
                      <BookOpen size={13} /> O‘qish va Tahlil
                    </button>
                    <button
                      className={`flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 font-medium transition-colors ${
                        activeTab === "plan" ? "bg-surface-2 text-ink" : "text-ink-muted hover:text-ink"
                      }`}
                      onClick={() => setActiveTab("plan")}
                    >
                      <ListTodo size={13} /> Reja
                    </button>
                    <button
                      className={`flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 font-medium transition-colors ${
                        activeTab === "flashcards" ? "bg-surface-2 text-ink" : "text-ink-muted hover:text-ink"
                      }`}
                      onClick={() => setActiveTab("flashcards")}
                    >
                      <Layers size={13} /> Kartalar
                    </button>
                    <button
                      className={`flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 font-medium transition-colors ${
                        activeTab === "concepts" ? "bg-surface-2 text-ink" : "text-ink-muted hover:text-ink"
                      }`}
                      onClick={() => setActiveTab("concepts")}
                    >
                      <Brain size={13} /> Tushunchalar
                    </button>
                  </div>
                )}
              </div>

              {selected.job.error_message && (
                <p role="alert" className="mb-4 rounded-xl border border-red-500/20 bg-red-500/10 p-3 text-sm text-red-600">
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
                  Bekor qilish
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
                    Qayta urinish
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
                          <span className="text-ink-muted">Shrift:</span>
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
                          <span className="text-ink-muted">Uslub:</span>
                          <button
                            className={`rounded px-2 py-0.5 ${
                              readerTheme === "default" ? "bg-surface-2 text-ink font-semibold" : "text-ink-faint"
                            }`}
                            onClick={() => setReaderTheme("default")}
                          >
                            Standart
                          </button>
                          <button
                            className={`rounded px-2 py-0.5 ${
                              readerTheme === "sepia" ? "bg-[#fbf0d9] text-[#5f4b32] font-semibold" : "text-ink-faint"
                            }`}
                            onClick={() => setReaderTheme("sepia")}
                          >
                            Sepia
                          </button>
                          <button
                            className={`rounded px-2 py-0.5 ${
                              readerTheme === "contrast" ? "bg-black text-white font-semibold" : "text-ink-faint"
                            }`}
                            onClick={() => setReaderTheme("contrast")}
                          >
                            Kontrast
                          </button>
                        </div>

                        {/* Progress Gauge */}
                        <div className="flex items-center gap-2">
                          <span className="text-ink-muted">{readPercent}% o‘qildi</span>
                          <div className="h-1.5 w-16 overflow-hidden rounded-full bg-surface-2">
                            <div className="h-full bg-accent" style={{ width: `${readPercent}%` }} />
                          </div>
                        </div>
                      </div>

                      {/* Section Dropdown */}
                      <label className="block">
                        <span className="mb-1 block text-xs font-semibold text-ink-muted">Bob / bo‘lim</span>
                        <select
                          className="block w-full rounded-lg border border-line bg-surface p-2.5 text-sm text-ink focus:border-accent focus:outline-none"
                          value={sectionStart ?? ""}
                          onChange={(e) => {
                            const start = e.target.value === "" ? null : Number(e.target.value);
                            setSectionStart(start);
                            setOffset(start ?? 0);
                          }}
                        >
                          <option value="">Boshidan o‘qish</option>
                          {sections.map((section, i) => (
                            <option key={section.start} value={section.start}>
                              {section.heading ?? (section.page ? `${section.page}-sahifa` : `${i + 1}-bo‘lim`)}
                            </option>
                          ))}
                        </select>
                      </label>

                      {/* Article Text View */}
                      <article
                        aria-label="Manba matni"
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
                            Oldingi
                          </button>
                          <span className="text-xs text-ink-muted">
                            {page?.offset ?? 0} / {page?.total_chars ?? 0} belgi
                          </span>
                          <button
                            className={button}
                            disabled={!page || !hasNextStudentPage(page)}
                            onClick={() => setOffset(offset + 4000)}
                          >
                            Keyingi
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
                                  setIndexNotice(`${next + result.indexed} parcha indekslandi.`);
                                  if (result.next_offset === null) {
                                    setIndexOffset(0);
                                    return;
                                  }
                                  if (result.next_offset <= next) throw new Error("Indeks holati mos kelmadi.");
                                  next = result.next_offset;
                                  setIndexOffset(next);
                                }
                              })
                            }
                          >
                            Semantik qidiruvni tayyorlash
                          </button>
                        )}
                      </div>

                      {indexNotice && <p role="status" className="text-xs text-accent">{indexNotice}</p>}

                      {/* AI Learning & Source-Linked Chat */}
                      <div className="mt-6 rounded-2xl border border-line bg-surface p-4">
                        <div className="flex flex-wrap items-center justify-between gap-3">
                          <h3 className="flex items-center gap-2 font-semibold text-ink">
                            <Sparkles size={16} className="text-accent" />
                            Manba asosida o‘rganish va savol-javob
                          </h3>
                          <label className="flex items-center gap-1.5 text-xs text-ink-muted">
                            Javob tili:
                            <select
                              value={language}
                              onChange={(e) => setLanguage(e.target.value)}
                              className="rounded border border-line bg-surface-2 p-1 text-xs text-ink"
                            >
                              <option value="uz">O‘zbek</option>
                              <option value="en">English</option>
                              <option value="ru">Русский</option>
                            </select>
                          </label>
                        </div>

                        <label htmlFor="student-question" className="mt-3 block text-xs font-semibold text-ink-muted">
                          Hujjat haqida savol
                        </label>
                        <input
                          id="student-question"
                          className="my-2 w-full rounded-lg border border-line bg-surface-2 p-3 text-sm text-ink placeholder:text-ink-faint focus:border-accent focus:outline-none"
                          placeholder="Savolingizni yozing yoki quyidagi tayyor tugmalardan foydalaning..."
                          value={question}
                          onChange={(e) => setQuestion(e.target.value)}
                          maxLength={2000}
                        />

                        <div className="flex flex-wrap gap-2">
                          {[
                            ["answer", "Javob olish"],
                            ["summary", "Bo‘lim xulosasi"],
                            ["study_guide", "O‘quv qo‘llanma"],
                            ["quiz", "Test tuzish"],
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
                                ? `AI izohi (${answer.provider}); tanlangan manba parchalari asosida. Citation tekshiruvi faktlarning to‘g‘riligini kafolatlamaydi.`
                                : "Yetarli dalil topilmadi."}
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
                                      choices[i] === item.answer ? "text-success" : "text-amber-600"
                                    }`}
                                  >
                                    {choices[i] === item.answer ? "To‘g‘ri." : "Qayta o‘ylab ko‘ring."}{" "}
                                    <span className="font-normal text-ink-muted">{item.explanation}</span>
                                  </p>
                                )}
                              </fieldset>
                            ))}

                            {/* Exact Citations */}
                            <h3 className="mt-2 font-semibold text-ink">Manbalar</h3>
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
                        <h3 className="font-bold text-ink">Bugungi takrorlash rejasi</h3>
                        <p className="text-xs text-ink-muted">
                          Saqlangan kartalaringizning haqiqiy takrorlash jadvalidan. Bu o‘zlashtirish bahosi yoki
                          avtomatik tuzilgan o‘quv dasturi emas.
                        </p>
                      </div>
                      {!practicePlan ? (
                        <p className="text-xs text-ink-muted">Yuklanmoqda…</p>
                      ) : practicePlan.items.length === 0 ? (
                        <p className="rounded-xl border border-dashed border-line p-4 text-center text-xs text-ink-muted">
                          {cards.length === 0
                            ? "Hali saqlangan karta yo‘q. “Flash-kartalar” bo‘limida manbadan karta yarating."
                            : "Hozir takrorlanadigan karta yo‘q."}
                        </p>
                      ) : (
                        <ol className="grid gap-2">
                          {practicePlan.items.map((item) => {
                            const card = cards.find((c) => c.id === item.card_id);
                            return (
                              <li key={item.card_id} className="rounded-xl border border-line bg-surface-2/40 p-3 text-sm">
                                <span className="font-semibold text-ink">{card?.front ?? "Karta"}</span>
                                <span className="ml-2 text-xs text-ink-muted">
                                  {item.reason === "scheduled_recall" ? "rejali takrorlash" : "birinchi yoki qayta takrorlash"} ·{" "}
                                  {new Date(item.due_at).toLocaleString()}
                                </span>
                              </li>
                            );
                          })}
                        </ol>
                      )}
                    </div>
                  )}

                  {/* TAB 3: Interactive Flashcards */}
                  {activeTab === "flashcards" && (
                    <div className="space-y-4 rounded-2xl border border-line bg-surface p-5">
                      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                        <div>
                          <h3 className="font-bold text-ink">Asosiy Tushunchalar bo‘yicha Flash-kartalar</h3>
                          <p className="text-xs text-ink-muted">
                            Manbadan iqtibos olingan kartalar. Spaced repetition orqali eslab qolishni mustahkamlang.
                          </p>
                        </div>
                        {progress && (
                          <div className="flex items-center gap-2 text-xs">
                            <span className="rounded-full bg-accent/10 px-2.5 py-1 font-medium text-accent border border-accent/20">
                              Faol: {progress.active_cards} ta
                            </span>
                            <span className="rounded-full bg-emerald-500/10 px-2.5 py-1 font-medium text-emerald-600 border border-emerald-500/20">
                              O‘rganilgan: {progress.reviewed_cards} ta
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
                                    <span className="font-mono">Karta v{card.version}</span>
                                    <span className="text-[11px] font-medium text-accent">
                                      {isFlipped ? "Ta'rif (Orqa)" : "Savol (Oldi — Flip)"}
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
                                    O‘chirish
                                  </button>
                                  <div className="flex items-center gap-1.5">
                                    <button
                                      type="button"
                                      className="px-2 py-0.5 rounded bg-surface-3 hover:bg-surface-2 text-[11px] text-ink font-medium"
                                      onClick={() => void handleReview(card, "again")}
                                    >
                                      Qayta
                                    </button>
                                    <button
                                      type="button"
                                      className="px-2 py-0.5 rounded bg-surface-3 hover:bg-surface-2 text-[11px] text-amber-600 font-medium"
                                      onClick={() => void handleReview(card, "hard")}
                                    >
                                      Qiyin
                                    </button>
                                    <button
                                      type="button"
                                      className="px-2 py-0.5 rounded bg-surface-3 hover:bg-surface-2 text-[11px] text-primary font-medium"
                                      onClick={() => void handleReview(card, "good")}
                                    >
                                      Yaxshi
                                    </button>
                                    <button
                                      type="button"
                                      className="px-2 py-0.5 rounded bg-surface-3 hover:bg-surface-2 text-[11px] text-emerald-600 font-medium"
                                      onClick={() => void handleReview(card, "easy")}
                                    >
                                      Oson
                                    </button>
                                  </div>
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      ) : (
                        <p className="rounded-xl border border-dashed border-line p-6 text-center text-xs text-ink-muted">
                          Hali saqlangan o‘quv kartalari yo‘q.
                        </p>
                      )}

                      <div className="space-y-3 border-t border-line pt-4">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <p className="text-xs text-ink-muted">
                            AI manbadan iqtibosli karta taklif qiladi; siz saqlamaguningizcha hech narsa yozilmaydi.
                          </p>
                          <button
                            type="button"
                            className={button}
                            disabled={busy || !provider}
                            onClick={() => void perform(proposeCards)}
                          >
                            Manbadan karta taklif qilish (AI)
                          </button>
                        </div>
                        {proposals.map((proposal, index) => (
                          <div key={`${proposal.chunk_id}-${proposal.quote_start}`} className="rounded-xl border border-line bg-surface-2/40 p-3 text-sm">
                            <p className="font-semibold text-ink">{proposal.front}</p>
                            <p className="mt-1 text-xs text-ink-muted">{proposal.back}</p>
                            <button type="button" className={`${button} mt-2`} onClick={() => void perform(() => saveProposal(index))}>
                              Saqlash
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
                          <h3 className="font-bold text-ink">Kitob Strukturasi va Konsept Daraxti</h3>
                          <p className="text-xs text-ink-muted">Hujjatning iyerarxik boblari va model talqini konsept grafi</p>
                        </div>
                        <button
                          type="button"
                          className={button}
                          disabled={conceptLoading || !provider}
                          onClick={() => void handleGenerateConceptGraph()}
                        >
                          {conceptLoading ? "Tahlil qilinmoqda..." : "Konsept grafini tahlil qilish (AI)"}
                        </button>
                      </div>

                      {conceptGraph && !conceptGraph.graph && (
                        <p role="status" className="rounded-xl border border-line p-3 text-xs text-ink-muted">
                          Konsept grafi uchun yetarli manba topilmadi.
                        </p>
                      )}
                      {conceptGraph?.graph && (
                        <div className="rounded-xl border border-primary/20 bg-primary/5 p-4 space-y-3">
                          <div className="flex items-center justify-between text-xs">
                            <span className="font-semibold text-primary">AI taklif qilgan konsept grafi</span>
                            <span className="text-ink-faint">Model talqini; iqtiboslar manbaga tekshirilgan</span>
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
                              <h5 className="text-xs font-semibold text-ink mb-1.5">Bog‘liqliklar:</h5>
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
                                  {sec.heading || `Bo‘lim ${idx + 1}`}
                                </h4>
                                <p className="text-xs text-ink-muted">
                                  Diapazon: {sec.start}–{sec.end} belgilar {sec.page ? `(${sec.page}-sahifa)` : ""}
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
                                O‘qishga o‘tish
                              </button>
                            </div>
                          ))
                        ) : (
                          <div className="rounded-xl border border-line bg-surface-2/20 p-4 text-center text-xs text-ink-muted">
                            Matn bo‘limlari indekslanmoqda yoki yagona yaxlit matn sifatida saqlangan.
                          </div>
                        )}
                      </div>
                    </div>
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
