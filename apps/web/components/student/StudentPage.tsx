"use client";

import { useCallback, useEffect, useState } from "react";
import { hasNextStudentPage, studentRequest } from "@/lib/student-api";
import { PageFrame } from "../pages/PageFrame";

type Job = { parser_version: string; id: string; document_id: string; project_id: string | null; state: string; attempts: number; max_attempts: number; error_message: string | null };
type Entry = { title: string; job: Job };
type Section = { start: number; end: number; heading: string | null; page: number | null };
type Page = { text: string; offset: number; total_chars: number };
type Citation = { n: number; excerpt: string; location: string };
type Quiz = { question: string; choices: string[]; answer: number; explanation: string };
type Learning = { status: string; text: string; generated: boolean; provider: string | null; citations: Citation[]; quiz: { items: Quiz[] } | null };

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
  const refresh = useCallback(async () => {
    const rows = await studentRequest<Entry[]>(`student/library?offset=${libraryOffset}&limit=31`);
    setEntries(rows.slice(0, 30));
    setMoreBooks(rows.length > 30);
    setSelected(current => current ? rows.find(e => e.job.id === current.job.id) ?? null : null);
  }, [libraryOffset]);
  useEffect(() => {
    let active = true;
    async function load() {
      try {
        await refresh();
        const status = await studentRequest<{ ai_provider_configured: boolean; embedding_provider_configured: boolean }>("student/status");
        if (active) { setProvider(status.ai_provider_configured); setEmbedding(status.embedding_provider_configured); }
      } catch (e) { if (active) setError(String(e)); }
    }
    void load();
    const timer = window.setInterval(() => { void refresh().catch(e => setError(String(e))); }, 2000);
    return () => { active = false; window.clearInterval(timer); };
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
    ]).then(([result, structure]) => { if (active) { setPage(result); setSections(structure.sections); } })
      .catch(e => { if (active) setError(String(e)); });
    return () => { active = false; };
  }, [selectedId, documentId, state, offset]);

  async function perform(action: () => Promise<void>) {
    setBusy(true); setError("");
    try { await action(); await refresh(); } catch (e) { setError(String(e)); } finally { setBusy(false); }
  }
  function choose(entry: Entry) {
    setSelected(entry); setOffset(0); setPage(null); setSections([]); setSectionStart(null); setAnswer(null); setChoices({}); setIndexOffset(0); setIndexNotice("");
  }
  async function learn(kind: string) {
    if (!selected) return;
    const result = await studentRequest<Learning>(`student/documents/${selected.job.document_id}/learn`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kind, question, language, section_start: sectionStart }),
    });
    setAnswer(result); setChoices({});
  }
  const button = "rounded-lg border border-line px-3 py-2 text-sm disabled:opacity-40";
  return <PageFrame title="EZO Student" subtitle="Manbani o‘qing, dalil bilan o‘rganing.">
    <p className="mb-4 text-sm text-ink-muted">PDF, EPUB, DOCX: 5 MiB gacha. Alohida xavfsiz worker talab qilinadi. Skanerlangan PDF uchun OCR hozircha mavjud emas.</p>
    {!provider && <p role="status" className="mb-4">AI provayder ulanmagan. O‘qish ishlaydi; AI javoblari, qo‘llanma va testlar uchun provayder kerak.</p>}
    {error && <p role="alert" className="mb-4 text-red-600">{error}</p>}
    <section aria-label="Hujjat yuklash" className="mb-6 grid gap-3">
      <label className="grid gap-2">Hujjat yuklash
        <input type="file" accept=".pdf,.epub,.docx" disabled={busy} onChange={e => {
          const file = e.target.files?.[0]; if (!file) return;
          if (file.size > 5 * 1024 * 1024) { setError("Fayl 5 MiB dan katta."); return; }
          void perform(async () => { await studentRequest("student/uploads?filename=" + encodeURIComponent(file.name), { method: "POST", body: file }); });
        }} />
      </label>
      <label htmlFor="student-text">Yoki o‘rganish uchun matn</label>
      <textarea id="student-text" value={text} onChange={e => setText(e.target.value)} maxLength={2000000} rows={3} className="rounded-lg border border-line p-3" />
      <button className={button} disabled={busy || !text.trim()} onClick={() => void perform(async () => {
        await studentRequest("student/readings", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text, title: "O‘quv matni" }) }); setText("");
      })}>Matnni saqlash</button>
    </section>
    <div className="grid gap-6 md:grid-cols-[220px_minmax(0,1fr)]">
      <nav aria-label="Hujjatlar kutubxonasi" className="grid content-start gap-2">
        <h2 className="font-semibold">Kutubxona</h2>
        {!entries.length && <p>Hali hujjat yo‘q.</p>}
        {entries.map(entry => <button key={entry.job.id} className={`${button} break-words text-left`} aria-pressed={entry.job.id === selectedId} onClick={() => choose(entry)}>
          {entry.title}<span className="block text-xs text-ink-muted">{({ queued: "Navbatda", running: "O‘qilmoqda", completed: "Tayyor", failed: "Xato", cancelled: "Bekor qilindi" })[entry.job.state] ?? entry.job.state}</span>
        </button>)}
        {entries.length > 0 && <p aria-live="polite" className="text-xs text-ink-muted">{libraryOffset + 1}–{libraryOffset + entries.length}</p>}
        <div className="flex flex-wrap gap-2">
          <button className={button} disabled={libraryOffset === 0} onClick={() => setLibraryOffset(Math.max(0, libraryOffset - 30))}>Oldingi hujjatlar</button>
          <button className={button} disabled={!moreBooks} onClick={() => setLibraryOffset(libraryOffset + 30)}>Keyingi hujjatlar</button>
        </div>
      </nav>
      <section className="min-w-0" aria-label="O‘qish va o‘rganish">
        {selected && <>
          <h2 className="mb-3 font-semibold">{selected.title}</h2>
          <p role="status">Urinishlar: {selected.job.attempts}/{selected.job.max_attempts}</p>
          {selected.job.error_message && <p role="alert">{selected.job.error_message}</p>}
          {["queued", "running"].includes(selected.job.state) && <button disabled={busy} className={button} onClick={() => void perform(async () => {
            await studentRequest(`knowledge/document-jobs/${selected.job.id}/cancel`, { method: "POST" });
          })}>Bekor qilish</button>}
          {selected.job.parser_version === "isolated-extraction/v1" && ["failed", "cancelled"].includes(selected.job.state) && <button disabled={busy} className={button} onClick={() => void perform(async () => {
            const job = await studentRequest<Job>(`student/readings/${selected.job.id}/retry`, { method: "POST" }); choose({ ...selected, job });
          })}>Qayta urinish</button>}
          {selected.job.state === "completed" && <>
            <label className="my-3 block">Bob / bo‘lim
              <select className="block w-full rounded-lg border border-line p-2" value={sectionStart ?? ""} onChange={e => { const start = e.target.value === "" ? null : Number(e.target.value); setSectionStart(start); setOffset(start ?? 0); }}>
                <option value="">Boshidan o‘qish</option>
                {sections.map((section, i) => <option key={section.start} value={section.start}>{section.heading ?? (section.page ? `${section.page}-sahifa` : `${i + 1}-bo‘lim`)}</option>)}
              </select>
            </label>
            <article aria-label="Manba matni" className="my-4 whitespace-pre-wrap break-words rounded-xl border border-line p-4">{page?.text}</article>
            <div className="flex flex-wrap items-center gap-2">
              <button className={button} disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 4000))}>Oldingi</button>
              <span>{page?.offset ?? 0} / {page?.total_chars ?? 0} belgi</span>
              <button className={button} disabled={!page || !hasNextStudentPage(page)} onClick={() => setOffset(offset + 4000)}>Keyingi</button>
            </div>
            {embedding && <button className={`${button} mt-4`} disabled={busy} onClick={() => void perform(async () => {
              let next = indexOffset;
              for (let batch = 0; batch < 100; batch++) {
                const result = await studentRequest<{ indexed: number; next_offset: number | null }>(`student/documents/${selected.job.document_id}/semantic-index?offset=${next}`, { method: "POST" });
                setIndexNotice(`${next + result.indexed} parcha indekslandi.`);
                if (result.next_offset === null) { setIndexOffset(0); return; }
                if (result.next_offset <= next) throw new Error("Indeks holati mos kelmadi.");
                next = result.next_offset; setIndexOffset(next);
              }
            })}>Semantik qidiruvni tayyorlash</button>}
            {indexNotice && <p role="status">{indexNotice}</p>}
            <label className="mt-4 block">Javob tili <select value={language} onChange={e => setLanguage(e.target.value)} className="rounded border border-line p-2"><option value="uz">O‘zbek</option><option value="en">English</option><option value="ru">Русский</option></select></label>
            <label htmlFor="student-question" className="mt-4 block">Hujjat haqida savol</label>
            <input id="student-question" className="my-2 w-full rounded-lg border border-line p-3" value={question} onChange={e => setQuestion(e.target.value)} maxLength={2000} />
            <div className="flex flex-wrap gap-2">
              {[["answer", "Javob olish"], ["summary", "Bo‘lim xulosasi"], ["study_guide", "O‘quv qo‘llanma"], ["quiz", "Test tuzish"]].map(([kind, label]) => <button className={button} key={kind} disabled={busy || !provider || (kind === "answer" && !question.trim())} onClick={() => void perform(() => learn(kind))}>{label}</button>)}
            </div>
            {answer && <div aria-live="polite" className="mt-4 grid gap-3">
              <p className="text-sm text-ink-muted">{answer.generated ? `AI izohi (${answer.provider}); tanlangan manba parchalari asosida. Citation tekshiruvi faktlarning to‘g‘riligini kafolatlamaydi.` : "Yetarli dalil topilmadi."}</p>
              {!answer.quiz && <p className="whitespace-pre-wrap break-words">{answer.text}</p>}
              {answer.quiz?.items.map((item, i) => <fieldset key={i} className="rounded-xl border border-line p-3"><legend>{item.question}</legend>
                {item.choices.map((choice, j) => <label key={j} className="my-2 block"><input type="radio" name={`quiz-${i}`} checked={choices[i] === j} onChange={() => setChoices({ ...choices, [i]: j })} /> {choice}</label>)}
                {choices[i] !== undefined && <p role="status">{choices[i] === item.answer ? "To‘g‘ri." : "Qayta o‘ylab ko‘ring."} {item.explanation}</p>}
              </fieldset>)}
              <h3 className="font-semibold">Manbalar</h3>
              {answer.citations.map(citation => <blockquote className="break-words border-l-2 border-line pl-3" key={citation.n}>[{citation.n}] {citation.location}<p>{citation.excerpt}</p></blockquote>)}
            </div>}
          </>}
        </>}
      </section>
    </div>
  </PageFrame>;
}
