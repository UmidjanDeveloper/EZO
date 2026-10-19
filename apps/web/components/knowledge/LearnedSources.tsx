"use client";

import type { KnowledgeLibrary, LearnedSource, LearnedSourceDetail, LearnedSourceStatus, LibraryCapabilityReport } from "@ezo/shared";
import { ApiError } from "@ezo/shared";
import { Badge, Button, Card, Spinner } from "@ezo/ui";
import { BookOpen, ChevronDown, Loader2, RotateCw, Search, ShieldAlert, Sparkles, Trash2, X } from "lucide-react";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { api } from "@/lib/api";
import { formatBytes } from "@/lib/download";
import { useI18n } from "@/lib/i18n/context";
import { useApiData } from "@/lib/use-api-data";
import { StatusBadge } from "./StatusBadge";

const RUNNING: LearnedSourceStatus[] = ["queued", "inspecting", "reading", "indexing"];
const TONES = {
  queued: "neutral",
  inspecting: "accent",
  reading: "accent",
  indexing: "accent",
  indexed: "success",
  partial: "warning",
  failed: "danger",
} as const;

/** Knowledge OS: sources EZO has learned (websites, GitHub repositories, PyPI / npm packages). */
export function LearnedSources() {
  const { m, f } = useI18n();
  const t = m.learning;
  const fetchSources = useCallback(() => api.learnedSources(), []);
  const { data: sources, error: loadError, reload } = useApiData(fetchSources);
  const fetchLibraries = useCallback(() => api.knowledgeLibraries(), []);
  const { data: libraries, reload: reloadLibraries } = useApiData(fetchLibraries);
  const [target, setTarget] = useState("");
  const [libraryName, setLibraryName] = useState("");
  const [maxPages, setMaxPages] = useState(25);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<{ tone: "info" | "error"; text: string } | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);

  // Reading runs in the background: refresh while any source is still being read.
  const running = sources?.some((source) => RUNNING.includes(source.status)) ?? false;
  useEffect(() => {
    if (!running) return;
    const timer = window.setTimeout(() => {
      reload();
      reloadLibraries();
    }, 2000);
    return () => window.clearTimeout(timer);
  }, [running, sources, reload, reloadLibraries]);

  async function act(action: () => Promise<void>) {
    setBusy(true);
    setNotice(null);
    try {
      await action();
    } catch (error) {
      setNotice({ tone: "error", text: error instanceof ApiError ? error.message : String(error) });
    } finally {
      setBusy(false);
      reload();
      reloadLibraries();
    }
  }

  function learn(event: FormEvent) {
    event.preventDefault();
    if (!target.trim()) return;
    void act(async () => {
      const source = await api.learnSource({
        target: target.trim(),
        library_name: libraryName.trim() || null,
        limits: { max_pages: maxPages },
      });
      setTarget("");
      setNotice({ tone: "info", text: source.created === false ? t.alreadyLearned : t.started });
    });
  }

  const byLibrary = new Map<string, LearnedSource[]>();
  for (const source of sources ?? []) {
    byLibrary.set(source.library_id, [...(byLibrary.get(source.library_id) ?? []), source]);
  }

  return (
    <section className="mt-10" data-testid="learned-sources">
      <h2 className="mb-1 flex items-center gap-2 text-base font-semibold">
        <BookOpen size={18} className="text-accent" /> {t.title}
      </h2>
      <p className="mb-3 text-sm text-ink-muted">{t.intro}</p>

      <form onSubmit={learn} className="grid gap-2 sm:grid-cols-[1fr_12rem_6rem_auto]">
        <label className="sr-only" htmlFor="learn-target">
          {t.target}
        </label>
        <input
          id="learn-target"
          value={target}
          onChange={(event) => setTarget(event.target.value)}
          placeholder={t.targetPlaceholder}
          className="h-10 min-w-0 rounded-xl border border-line bg-surface px-3 text-sm focus:border-accent/60 focus:outline-none"
          data-testid="learn-target"
        />
        <label className="sr-only" htmlFor="learn-library">
          {t.library}
        </label>
        <input
          id="learn-library"
          list="learn-libraries"
          value={libraryName}
          onChange={(event) => setLibraryName(event.target.value)}
          placeholder={t.defaultLibrary}
          className="h-10 min-w-0 rounded-xl border border-line bg-surface px-3 text-sm focus:border-accent/60 focus:outline-none"
          data-testid="learn-library"
        />
        <datalist id="learn-libraries">
          {(libraries ?? []).map((library) => (
            <option key={library.id} value={library.name} />
          ))}
        </datalist>
        <label className="sr-only" htmlFor="learn-pages">
          {t.maxPages}
        </label>
        <input
          id="learn-pages"
          type="number"
          min={1}
          max={200}
          value={maxPages}
          title={t.maxPages}
          onChange={(event) => setMaxPages(Math.max(1, Math.min(200, Number(event.target.value) || 1)))}
          className="h-10 rounded-xl border border-line bg-surface px-3 text-sm focus:border-accent/60 focus:outline-none"
        />
        <Button type="submit" disabled={busy || !target.trim()} data-testid="learn-submit">
          {t.learn}
        </Button>
      </form>
      <p className="mt-1 text-xs text-ink-faint">{t.formHint}</p>

      {notice ? (
        <p
          className={notice.tone === "error" ? "mt-3 text-sm text-danger" : "mt-3 text-sm text-ink-muted"}
          role={notice.tone === "error" ? "alert" : "status"}
          data-testid="learn-notice"
        >
          {notice.text}
        </p>
      ) : null}

      <div className="mt-5 flex flex-col gap-5">
        {loadError ? <p className="text-sm text-danger">{loadError.message}</p> : null}
        {!sources || !libraries ? (
          <Spinner label={m.common.loading} />
        ) : sources.length === 0 && libraries.length === 0 ? (
          <p className="py-4 text-center text-sm text-ink-muted" data-testid="learned-empty">
            {t.empty}
          </p>
        ) : (
          // Every library is shown, also an empty one, so it can be removed.
          libraries.map((library) => (
            <LibraryGroup
              key={library.id}
              library={library}
              sources={byLibrary.get(library.id) ?? []}
              openId={openId}
              busy={busy}
              onToggle={(id) => setOpenId(openId === id ? null : id)}
              onRefresh={(source) => void act(async () => void (await api.refreshLearnedSource(source.id)))}
              onDelete={(source) => {
                if (!window.confirm(f(t.confirmDelete, { name: source.title }))) return;
                void act(() => api.deleteLearnedSource(source.id));
              }}
              onDeleteLibrary={() => {
                if (!window.confirm(f(t.confirmDeleteLibrary, { name: library.name }))) return;
                void act(() => api.deleteKnowledgeLibrary(library.id));
              }}
            />
          ))
        )}
      </div>
    </section>
  );
}

function LibraryGroup({
  library,
  sources,
  openId,
  busy,
  onToggle,
  onRefresh,
  onDelete,
  onDeleteLibrary,
}: {
  library: KnowledgeLibrary;
  sources: LearnedSource[];
  openId: string | null;
  busy: boolean;
  onToggle: (id: string) => void;
  onRefresh: (source: LearnedSource) => void;
  onDelete: (source: LearnedSource) => void;
  onDeleteLibrary: () => void;
}) {
  const { m, f } = useI18n();
  const t = m.learning;
  const running = sources.some((source) => RUNNING.includes(source.status));
  const [searchQuery, setSearchQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const [searchResults, setSearchResults] = useState<Array<{ title: string; excerpt: string; url?: string | null }> | null>(null);
  const [showCapabilities, setShowCapabilities] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [capabilitiesReport, setCapabilitiesReport] = useState<LibraryCapabilityReport | null>(null);

  async function handleAnalyze() {
    setAnalyzing(true);
    try {
      const report = await api.analyzeKnowledgeLibrary(library.id);
      setCapabilitiesReport(report);
      setShowCapabilities(true);
    } catch {
      setCapabilitiesReport(null);
    } finally {
      setAnalyzing(false);
    }
  }

  async function handleSearch(e: FormEvent) {
    e.preventDefault();
    if (!searchQuery.trim()) return;
    setSearching(true);
    try {
      const res = await api.searchKnowledge(searchQuery.trim(), { libraryId: library.id });
      setSearchResults((res.results || []) as Array<{ title: string; excerpt: string; url?: string | null }>);
    } catch {
      setSearchResults([]);
    } finally {
      setSearching(false);
    }
  }

  function clearSearch() {
    setSearchQuery("");
    setSearchResults(null);
  }

  return (
    <div data-testid="learned-library" className="rounded-xl border border-line bg-surface/50 p-3">
      <div className="mb-2 flex items-center gap-2">
        <h3 className="text-sm font-medium">{library.name}</h3>
        <span className="text-xs text-ink-faint">{sources.length}</span>
        <div className="ml-auto flex items-center gap-1.5">
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={handleAnalyze}
            disabled={busy || running || analyzing || sources.length === 0}
            className="h-8 gap-1 text-xs"
            data-testid={`analyze-capabilities-${library.id}`}
          >
            {analyzing ? <Loader2 size={12} className="animate-spin" /> : <Sparkles size={12} className="text-accent" />}
            {analyzing ? t.analyzingCapabilities : t.analyzeCapabilities}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={onDeleteLibrary}
            disabled={busy || running}
            aria-label={m.learning.deleteLibrary}
          >
            <Trash2 size={14} />
          </Button>
        </div>
      </div>

      {/* Library-Scoped Search */}
      <form onSubmit={handleSearch} className="mb-3 flex items-center gap-2">
        <div className="relative flex-1">
          <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-ink-faint" />
          <input
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder={t.searchPlaceholder}
            className="h-8 w-full rounded-lg border border-line bg-surface pl-8 pr-7 text-xs focus:border-accent/60 focus:outline-none"
            data-testid={`library-search-input-${library.id}`}
          />
          {searchQuery ? (
            <button
              type="button"
              onClick={clearSearch}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-ink-faint hover:text-ink"
            >
              <X size={12} />
            </button>
          ) : null}
        </div>
        <Button
          type="submit"
          variant="secondary"
          size="sm"
          disabled={searching || !searchQuery.trim()}
          className="h-8 text-xs"
          data-testid={`library-search-btn-${library.id}`}
        >
          {searching ? <Loader2 size={12} className="animate-spin" /> : t.searchButton}
        </Button>
      </form>

      {/* Capabilities Proposal Panel */}
      {showCapabilities && capabilitiesReport ? (
        <div className="mb-3 rounded-lg border border-accent/25 bg-surface p-3 text-xs" data-testid={`capabilities-panel-${library.id}`}>
          <div className="mb-2 flex items-center justify-between border-b border-line/60 pb-2">
            <div>
              <div className="flex items-center gap-1.5 font-medium text-ink">
                <Sparkles size={14} className="text-accent" />
                <span>{t.capabilitiesTitle}</span>
                <span className="rounded bg-accent/15 px-1.5 py-0.2 text-[10px] font-medium text-accent">
                  {t.proposalBadge}
                </span>
              </div>
              <p className="mt-0.5 text-[11px] text-ink-faint">{t.capabilitiesSubtitle}</p>
            </div>
            <button
              type="button"
              onClick={() => setShowCapabilities(false)}
              className="text-ink-faint hover:text-ink"
              aria-label="Close"
            >
              <X size={14} />
            </button>
          </div>

          {capabilitiesReport.proposals.length === 0 ? (
            <p className="py-2 text-center text-xs text-ink-faint">{t.noCapabilities}</p>
          ) : (
            <div className="flex flex-col gap-2.5">
              {capabilitiesReport.proposals.map((p) => (
                <div key={p.id} className="rounded-md border border-line/70 bg-surface/70 p-2.5">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-ink">{p.title}</span>
                    <div className="flex items-center gap-1">
                      <span className="rounded bg-surface-muted px-1.5 py-0.5 text-[10px] text-ink-muted">{p.category}</span>
                      <span className={`rounded px-1.5 py-0.5 text-[10px] ${
                        p.relevance === "high" ? "bg-accent/15 text-accent font-medium" : "bg-surface-muted text-ink-muted"
                      }`}>
                        {t.relevance}: {t.relevanceLevels[p.relevance]}
                      </span>
                    </div>
                  </div>
                  <p className="mt-1 text-ink-muted">{p.description}</p>
                  <div className="mt-2 grid grid-cols-1 gap-1.5 border-t border-line/40 pt-1.5 sm:grid-cols-2 text-[11px]">
                    <div>
                      <span className="font-medium text-ink-muted">{t.existingCoverage}: </span>
                      <span className="text-ink-faint">
                        {p.existing_equivalents.length > 0
                          ? p.existing_equivalents.map((e) => `${e.kind}:${e.name} (${e.coverage})`).join(", ")
                          : "Yo'q"}
                      </span>
                    </div>
                    <div>
                      <span className="font-medium text-ink-muted">{t.missingFunctionality}: </span>
                      <span className="text-ink-faint">{p.missing_functionality}</span>
                    </div>
                  </div>
                  {p.required_dependencies.length > 0 ? (
                    <div className="mt-1 text-[11px]">
                      <span className="font-medium text-ink-muted">{t.requiredDeps}: </span>
                      <span className="font-mono text-ink-faint">{p.required_dependencies.join(", ")}</span>
                    </div>
                  ) : null}
                  {p.evidence.length > 0 ? (
                    <div className="mt-1.5 rounded bg-surface-muted/40 p-1.5 text-[11px]">
                      <span className="font-medium text-ink-muted">{t.evidenceTitle}:</span>
                      {p.evidence.slice(0, 1).map((ev, i) => (
                        <p key={i} className="mt-0.5 italic text-ink-faint">
                          [{t.evidenceLevels[ev.evidence_level]}] {ev.title}: “{ev.excerpt.slice(0, 120)}…”
                        </p>
                      ))}
                    </div>
                  ) : null}
                  {p.recommended_next_step ? (
                    <p className="mt-1 text-[10px] text-ink-faint">
                      <span className="font-medium text-ink-muted">{t.nextStep}:</span> {p.recommended_next_step}
                    </p>
                  ) : null}
                </div>
              ))}
            </div>
          )}
        </div>
      ) : null}

      {/* Search results */}
      {searchResults !== null ? (
        <div className="mb-3 rounded-lg border border-accent/20 bg-accent/5 p-2.5" data-testid="library-search-results">
          <div className="mb-1.5 flex items-center justify-between text-xs font-medium text-accent">
            <span>{f(t.searchResults, { n: searchResults.length })}</span>
            <button type="button" onClick={clearSearch} className="text-[11px] text-ink-muted hover:text-ink underline">
              {t.allDocuments}
            </button>
          </div>
          {searchResults.length === 0 ? (
            <p className="py-2 text-center text-xs text-ink-muted">{t.noResults}</p>
          ) : (
            <div className="flex flex-col gap-1.5">
              {searchResults.map((res, i) => (
                <div key={i} className="rounded border border-line bg-surface p-2 text-xs">
                  <div className="font-medium text-ink">{res.title}</div>
                  <p className="mt-0.5 text-ink-muted line-clamp-2">{res.excerpt}</p>
                </div>
              ))}
            </div>
          )}
        </div>
      ) : null}

      <div className="flex flex-col gap-2">
        {sources.map((source) => (
          <SourceRow
            key={source.id}
            source={source}
            open={openId === source.id}
            busy={busy}
            onToggle={() => onToggle(source.id)}
            onRefresh={() => onRefresh(source)}
            onDelete={() => onDelete(source)}
          />
        ))}
      </div>
    </div>
  );
}

function SourceRow({
  source,
  open,
  busy,
  onToggle,
  onRefresh,
  onDelete,
}: {
  source: LearnedSource;
  open: boolean;
  busy: boolean;
  onToggle: () => void;
  onRefresh: () => void;
  onDelete: () => void;
}) {
  const { m, f } = useI18n();
  const t = m.learning;
  const running = RUNNING.includes(source.status);
  const review = source.profile.license_review;
  const stats = source.stats;
  const [detail, setDetail] = useState<LearnedSourceDetail | null>(null);
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    void api
      .learnedSource(source.id)
      .then((value) => !cancelled && setDetail(value))
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [open, source.id, source.status]);

  return (
    <Card className="px-4 py-3" data-testid="learned-source" data-status={source.status}>
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={open}
          className="flex min-w-0 flex-1 items-center gap-2 text-left"
        >
          <ChevronDown size={16} className={open ? "rotate-180 transition-transform" : "transition-transform"} />
          <span className="truncate text-sm font-medium">{source.title}</span>
        </button>
        <Badge tone="neutral">{t.kinds[source.kind]}</Badge>
        <Badge tone={TONES[source.status]} data-testid="learned-status">
          {running ? <Loader2 size={11} className="animate-spin" /> : null}
          {t.status[source.status]}
        </Badge>
        <Button variant="ghost" size="sm" onClick={onRefresh} disabled={busy || running} aria-label={t.refresh}>
          <RotateCw size={14} />
        </Button>
        <Button
          variant="ghost"
          size="sm"
          onClick={onDelete}
          disabled={busy || running}
          aria-label={t.delete}
          data-testid="learned-delete"
        >
          <Trash2 size={14} />
        </Button>
      </div>
      <p className="mt-1 text-xs text-ink-faint">
        {[
          source.version ? f(t.version, { v: source.version }) : null,
          source.license ? f(t.license, { l: source.license }) : t.noLicense,
          stats.documents !== undefined ? f(t.read, { n: stats.documents, k: stats.keyword_only ?? 0 }) : null,
          stats.stopped ? t.stopped[stats.stopped as keyof typeof t.stopped] ?? stats.stopped : null,
        ]
          .filter(Boolean)
          .join(" · ")}
      </p>
      {review?.needs_review ? (
        <p className="mt-1 text-xs text-warning" data-testid="learned-license-review">
          {t.licenseReview}
        </p>
      ) : null}
      {source.security_flags.length ? (
        <p className="mt-1 flex items-center gap-1 text-xs text-warning" data-testid="learned-flags">
          <ShieldAlert size={13} /> {f(t.flags, { n: source.security_flags.length })}
        </p>
      ) : null}
      {source.profile.access === "raw_fallback" ? (
        <p className="mt-1 text-xs text-ink-muted">{t.rawFallback}</p>
      ) : null}
      {source.error ? (
        <p className="mt-1 text-xs text-danger" data-testid="learned-error">
          {source.error}
        </p>
      ) : null}
      {open ? (
        <div className="mt-3 border-t border-line pt-3 text-xs">
          <p className="mb-2 break-all text-ink-muted">
            {source.target}
            {source.profile.description ? ` — ${source.profile.description}` : ""}
          </p>
          {review ? <p className="mb-2 text-ink-muted">{review.note}</p> : null}
          {source.security_flags.slice(0, 5).map((flag, index) => (
            <p key={index} className="mb-1 rounded-lg bg-warning/5 px-2 py-1 text-ink-muted">
              <span className="font-medium">{flag.kind}</span> · {flag.location}: “{flag.excerpt}”
            </p>
          ))}
          {!detail ? (
            <Spinner label={m.common.loading} />
          ) : (
            <ul className="divide-y divide-line" data-testid="learned-documents">
              {detail.documents.map((document) => (
                <li key={document.id} className="flex items-center gap-2 py-1.5">
                  <a
                    href={document.url ?? undefined}
                    target="_blank"
                    rel="noreferrer noopener"
                    className="min-w-0 flex-1 truncate hover:underline"
                  >
                    {document.title}
                  </a>
                  <span className="text-ink-faint">
                    {document.size_bytes ? formatBytes(document.size_bytes) : ""}
                  </span>
                  <StatusBadge status={document.status} />
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : null}
    </Card>
  );
}
