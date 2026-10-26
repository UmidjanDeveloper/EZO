"use client";

import { Button, Card, cn, Spinner, TextAreaField, TextField } from "@ezo/ui";
import {
  CheckCircle2,
  Download,
  Eye,
  FileText,
  Play,
  Presentation,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { useCallback, useState, type FormEvent } from "react";
import { api, apiUrl, storedToken } from "@/lib/api";
import { saveBlob } from "@/lib/download";
import { useI18n } from "@/lib/i18n/context";
import { useApiData } from "@/lib/use-api-data";
import { PageFrame } from "./PageFrame";

interface ThemeInfo {
  name: string;
  dark: boolean;
  background: string;
  surface: string;
  ink: string;
  accent: string;
  chart_palette: string[];
}

interface SlideOutline {
  slide_number: number;
  layout: string;
  title: string;
  summary: string;
  bullet_hints: string[];
}

interface PresentationOutline {
  title: string;
  theme: string;
  language: string;
  slide_count: number;
  slides: SlideOutline[];
  /** "model": planned by the configured AI for this topic; "template": EZO's fixed structure. */
  source?: "model" | "template";
  notice?: string;
  /** The validated model deck; built as-is (charts, tables) when present. */
  deck?: Record<string, unknown> | null;
}

interface GeneratedArtifact {
  artifact_id: string;
  title: string;
  theme: string;
  slide_count: number;
  pptx_download_url: string;
  pdf_download_url: string;
  html_preview_url: string;
  qa_report: Record<string, unknown>;
}

export function PresentationsPage() {
  const { m, f } = useI18n();

  const authHeaders = useCallback(() => {
    const token = storedToken.get().trim();
    return {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    };
  }, []);

  // Themes
  const fetchThemes = useCallback(async () => {
    const res = await fetch(`${apiUrl()}/api/presentations/themes`, { headers: authHeaders() });
    return res.ok ? ((await res.json()) as ThemeInfo[]) : [];
  }, [authHeaders]);
  const { data: themesData } = useApiData(fetchThemes);
  const themes = themesData ?? [];

  const [selectedTheme, setSelectedTheme] = useState("ezo");

  // Brief state
  const [title, setTitle] = useState(m.presentations.sampleTitle);
  const [topic, setTopic] = useState(m.presentations.sampleTopic);
  const [audience, setAudience] = useState(m.presentations.sampleAudience);
  const [slideCount, setSlideCount] = useState(6);
  const [keyPoints, setKeyPoints] = useState(m.presentations.sampleKeyPoints);

  // Outline & Generation state
  const [loadingOutline, setLoadingOutline] = useState(false);
  const [loadingPptx, setLoadingPptx] = useState(false);
  const [outline, setOutline] = useState<PresentationOutline | null>(null);
  const [generated, setGenerated] = useState<GeneratedArtifact | null>(null);
  const [error, setError] = useState<string | null>(null);

  /** Downloads with the owner's bearer token (plain links get 401 in token mode). */
  async function download(artifactId: string, format?: "pdf" | "html") {
    try {
      const detail = await api.getArtifact(artifactId);
      const version = detail.current_version;
      if (!version) throw new Error(m.presentations.versionNotFound);
      const result = format
        ? await api.downloadExport(artifactId, version.version_number, format)
        : await api.downloadArtifact(artifactId, version.version_number);
      if (format === "html") {
        window.open(URL.createObjectURL(result.blob), "_blank", "noopener");
      } else {
        saveBlob(result.blob, result.filename);
      }
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function handleGenerateOutline(e: FormEvent) {
    e.preventDefault();
    if (!title.trim() || !topic.trim()) return;
    setLoadingOutline(true);
    setError(null);
    try {
      const pts = keyPoints
        .split(",")
        .map((p) => p.trim())
        .filter(Boolean);
      const res = await fetch(`${apiUrl()}/api/presentations/intake`, {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify({
          title: title.trim(),
          topic: topic.trim(),
          audience: audience.trim(),
          slide_count: Number(slideCount),
          theme: selectedTheme,
          language: "uz",
          key_points: pts,
        }),
      });
      if (res.ok) {
        const data = (await res.json()) as PresentationOutline;
        setOutline(data);
        setGenerated(null);
      } else {
        setError(m.presentations.outlineError);
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoadingOutline(false);
    }
  }

  async function handleGeneratePptx() {
    if (!outline) return;
    setLoadingPptx(true);
    setError(null);
    try {
      const res = await fetch(`${apiUrl()}/api/presentations/generate`, {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify({
          title: outline.title,
          theme: outline.theme,
          language: outline.language,
          ...(outline.deck ? { deck: outline.deck } : { slides: outline.slides }),
        }),
      });
      if (res.ok) {
        const data = (await res.json()) as GeneratedArtifact;
        setGenerated(data);
      } else {
        setError(m.presentations.pptxError);
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoadingPptx(false);
    }
  }

  return (
    <PageFrame
      title={m.presentations.title}
      subtitle={m.presentations.subtitle}
    >
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        {/* Left Column: Brief Intake Form (5 cols) */}
        <div className="space-y-6 lg:col-span-5">
          <Card className="space-y-4">
            <div className="flex items-center gap-2 border-b border-line pb-3">
              <Presentation size={18} className="text-accent" />
              <h3 className="text-sm font-semibold text-ink">
                {m.presentations.briefTitle}
              </h3>
            </div>

            <form onSubmit={handleGenerateOutline} className="space-y-3">
              <TextField
                label={m.presentations.topicLabel}
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                required
              />

              <TextAreaField
                label={m.presentations.detailsLabel}
                value={topic}
                onChange={(e) => setTopic(e.target.value)}
                rows={3}
                required
              />

              <div className="grid grid-cols-2 gap-3">
                <TextField
                  label={m.presentations.audienceLabel}
                  value={audience}
                  onChange={(e) => setAudience(e.target.value)}
                />
                <TextField
                  label={m.presentations.slidesCountLabel}
                  type="number"
                  min={3}
                  max={25}
                  value={String(slideCount)}
                  onChange={(e) => setSlideCount(Number(e.target.value))}
                />
              </div>

              {/* Theme Picker */}
              <div>
                <label className="mb-1.5 block text-xs font-medium text-ink">
                  {m.presentations.themeLabel}
                </label>
                <div className="grid grid-cols-3 gap-2">
                  {themes.slice(0, 6).map((thm) => (
                    <div
                      key={thm.name}
                      onClick={() => setSelectedTheme(thm.name)}
                      className={cn(
                        "cursor-pointer rounded-lg border p-2 text-center transition-all",
                        selectedTheme === thm.name
                          ? "border-accent ring-1 ring-accent"
                          : "border-line hover:border-accent/40",
                      )}
                      style={{ backgroundColor: thm.background }}
                    >
                      <div
                        className="mx-auto mb-1 h-3 w-6 rounded-sm"
                        style={{ backgroundColor: thm.accent }}
                      />
                      <span
                        className="block truncate text-[11px] font-medium"
                        style={{ color: thm.ink }}
                      >
                        {thm.name}
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              <TextField
                label={m.presentations.keyPointsLabel}
                value={keyPoints}
                onChange={(e) => setKeyPoints(e.target.value)}
              />

              {error ? <p className="text-xs text-danger">{error}</p> : null}

              <Button
                type="submit"
                variant="primary"
                className="w-full"
                disabled={loadingOutline}
                icon={<Sparkles size={16} />}
              >
                {loadingOutline ? <Spinner /> : m.presentations.generateOutline}
              </Button>
            </form>
          </Card>
        </div>

        {/* Right Column: Slide Outline & PPTX Generation Output (7 cols) */}
        <div className="space-y-6 lg:col-span-7">
          {generated ? (
            <Card className="space-y-4 border-success/40 bg-success/5">
              <div className="flex items-center gap-3">
                <div className="rounded-xl bg-success/10 p-3 text-success">
                  <CheckCircle2 size={24} />
                </div>
                <div>
                  <h3 className="text-base font-semibold text-ink">
                    {m.presentations.ready}
                  </h3>
                  <p className="text-xs text-ink-muted">
                    {f(m.presentations.generatedMeta, { title: generated.title, count: generated.slide_count, theme: generated.theme })}
                  </p>
                </div>
              </div>

              {/* Action Buttons */}
              <div className="flex flex-wrap items-center gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => void download(generated.artifact_id)}
                  className="flex items-center gap-2 rounded-xl bg-accent px-4 py-2 text-sm font-semibold text-white shadow-sm transition-opacity hover:opacity-90"
                >
                  <Download size={16} />
                  {m.presentations.downloadPptx}
                </button>
                <button
                  type="button"
                  onClick={() => void download(generated.artifact_id, "pdf")}
                  className="flex items-center gap-2 rounded-xl border border-line bg-surface px-4 py-2 text-sm font-medium text-ink transition-colors hover:border-accent/40"
                >
                  <FileText size={16} />
                  {m.presentations.downloadPdf}
                </button>
                <button
                  type="button"
                  onClick={() => void download(generated.artifact_id, "html")}
                  className="flex items-center gap-2 rounded-xl border border-line bg-surface px-4 py-2 text-sm font-medium text-ink transition-colors hover:border-accent/40"
                >
                  <Eye size={16} />
                  {m.presentations.previewHtml}
                </button>
              </div>

              {/* QA Badge */}
              <div className="mt-3 flex items-center gap-2 rounded-lg bg-surface-2 p-2.5 text-xs text-ink-muted">
                <ShieldCheck size={16} className="text-success" />
                <span>{m.presentations.qaPassed}</span>
              </div>
            </Card>
          ) : null}

          {outline ? (
            <Card className="space-y-4">
              <div className="flex items-center justify-between border-b border-line pb-3">
                <div>
                  <h3 className="text-sm font-semibold text-ink">
                    {m.presentations.outlineTitle}
                  </h3>
                  <p className="text-xs text-ink-muted">
                    {f(m.presentations.outlineMeta, { count: outline.slides.length, theme: outline.theme })} ·{" "}
                    <span data-testid="outline-source">
                      {outline.source === "model" ? m.presentations.sourceModel : m.presentations.sourceTemplate}
                    </span>
                  </p>
                  {outline.notice ? (
                    <p className="mt-1 text-xs text-amber-600" data-testid="outline-notice">
                      {outline.notice}
                    </p>
                  ) : null}
                </div>

                <Button
                  variant="primary"
                  size="sm"
                  disabled={loadingPptx}
                  icon={<Play size={14} />}
                  onClick={() => void handleGeneratePptx()}
                >
                  {loadingPptx ? <Spinner /> : m.presentations.createPptx}
                </Button>
              </div>

              {/* Slides outline list */}
              <div className="space-y-2.5">
                {outline.slides.map((s) => (
                  <div
                    key={s.slide_number}
                    className="flex items-start gap-3 rounded-xl border border-line bg-surface p-3 transition-colors hover:border-accent/30"
                  >
                    <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-surface-2 text-xs font-bold text-ink">
                      {s.slide_number}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-semibold text-ink">{s.title}</span>
                        <span className="rounded bg-surface-2 px-1.5 py-0.5 text-[10px] font-medium uppercase text-ink-muted">
                          {s.layout}
                        </span>
                      </div>
                      <p className="mt-1 text-xs text-ink-muted">{s.summary}</p>
                      {s.bullet_hints.length > 0 ? (
                        <div className="mt-1.5 flex flex-wrap gap-1">
                          {s.bullet_hints.map((b, idx) => (
                            <span
                              key={idx}
                              className="rounded-md border border-line bg-surface-2/60 px-2 py-0.5 text-[11px] text-ink-muted"
                            >
                              • {b}
                            </span>
                          ))}
                        </div>
                      ) : null}
                    </div>
                  </div>
                ))}
              </div>
            </Card>
          ) : (
            <Card className="flex flex-col items-center justify-center p-8 text-center">
              <Presentation size={48} className="mb-3 text-accent" />
              <h3 className="text-base font-semibold text-ink">{m.presentations.emptyTitle}</h3>
              <p className="mt-1 max-w-sm text-xs text-ink-muted">{m.presentations.emptyDesc}</p>
            </Card>
          )}
        </div>
      </div>
    </PageFrame>
  );
}
