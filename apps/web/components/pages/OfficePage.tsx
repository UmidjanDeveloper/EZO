"use client";

import { Button, Card, cn, TextAreaField, TextField } from "@ezo/ui";
import {
  CheckCircle2,
  Download,
  FileSpreadsheet,
  FileText,
  ShieldCheck,
  Table as TableIcon,
} from "lucide-react";
import { useCallback, useState, type FormEvent } from "react";
import { apiUrl, storedToken } from "@/lib/api";
import { useI18n } from "@/lib/i18n/context";
import { useApiData } from "@/lib/use-api-data";
import { PageFrame } from "./PageFrame";

type OfficeTab = "document" | "spreadsheet" | "artifacts";

interface OfficeTemplate {
  id: string;
  title: string;
  type: "docx" | "xlsx";
  category: string;
  description: string;
  sample_content: {
    markdown?: string;
    columns?: string[];
    rows?: (string | number)[][];
  };
}

interface OfficeArtifact {
  artifact_id: string;
  title: string;
  type: string;
  filename: string;
  download_url: string;
  exports: Record<string, string>;
  created_at: string;
}

export function OfficePage() {
  const { m } = useI18n();
  const [activeTab, setActiveTab] = useState<OfficeTab>("document");

  const authHeaders = useCallback(() => {
    const token = storedToken.get().trim();
    return {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    };
  }, []);

  // Templates
  const fetchTemplates = useCallback(async () => {
    const res = await fetch(`${apiUrl()}/api/office/templates`, { headers: authHeaders() });
    return res.ok ? ((await res.json()) as OfficeTemplate[]) : [];
  }, [authHeaders]);
  const { data: templatesData } = useApiData(fetchTemplates);
  const templates = templatesData ?? [];

  // Artifacts
  const fetchArtifacts = useCallback(async () => {
    const res = await fetch(`${apiUrl()}/api/office/artifacts`, { headers: authHeaders() });
    return res.ok ? ((await res.json()) as OfficeArtifact[]) : [];
  }, [authHeaders]);
  const { data: artifactsData, reload: reloadArtifacts } = useApiData(fetchArtifacts);
  const artifacts = artifactsData ?? [];

  // Document creation form
  const [docTitle, setDocTitle] = useState("Rasmiy murojaat xati");
  const [docMarkdown, setDocMarkdown] = useState(
    "# RASMIY XAT\n\n**Kimga:** Tashkilot rahbariyatiga\n\n**Mavzu:** Hamkorlik loyihasi to'g'risida\n\nHurmatli hamkasblar!\n\nMazkur xat orqali ta'lim va axborot texnologiyalari sohasida hamkorlik qilish istagimizni bildiramiz.",
  );
  const [exportPdf, setExportPdf] = useState(true);

  // Spreadsheet creation form
  const [sheetTitle, setSheetTitle] = useState("Oylik daromad va xarajatlar");
  const [columnsStr, setColumnsStr] = useState("Modda, Reja (UZS), Haqiqat (UZS), Farq (UZS)");
  const [rowsData, setRowsData] = useState(
    "Infratuzilma, 12000000, 11500000, -500000\nMaoshlar, 45000000, 45000000, 0\nMarketing, 8000000, 9200000, 1200000",
  );

  const [loading, setLoading] = useState(false);
  const [recentSuccess, setRecentSuccess] = useState<OfficeArtifact | null>(null);
  const [error, setError] = useState<string | null>(null);

  function applyTemplate(tmpl: OfficeTemplate) {
    if (tmpl.type === "docx") {
      setActiveTab("document");
      setDocTitle(tmpl.title);
      if (tmpl.sample_content.markdown) {
        setDocMarkdown(tmpl.sample_content.markdown);
      }
    } else {
      setActiveTab("spreadsheet");
      setSheetTitle(tmpl.title);
      if (tmpl.sample_content.columns) {
        setColumnsStr(tmpl.sample_content.columns.join(", "));
      }
      if (tmpl.sample_content.rows) {
        setRowsData(tmpl.sample_content.rows.map((r) => r.join(", ")).join("\n"));
      }
    }
  }

  async function handleCreateDocument(e: FormEvent) {
    e.preventDefault();
    if (!docTitle.trim() || !docMarkdown.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${apiUrl()}/api/office/documents`, {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify({
          title: docTitle.trim(),
          markdown: docMarkdown.trim(),
          export_pdf: exportPdf,
        }),
      });
      if (res.ok) {
        const art = (await res.json()) as OfficeArtifact;
        setRecentSuccess(art);
        reloadArtifacts();
      } else {
        setError("Hujjatni shakllantirishda xatolik yuz berdi.");
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  async function handleCreateSpreadsheet(e: FormEvent) {
    e.preventDefault();
    if (!sheetTitle.trim() || !columnsStr.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const cols = columnsStr
        .split(",")
        .map((c) => c.trim())
        .filter(Boolean);
      const rows = rowsData
        .split("\n")
        .map((line) => line.trim())
        .filter(Boolean)
        .map((line) =>
          line.split(",").map((cell) => {
            const trimmed = cell.trim();
            const num = Number(trimmed);
            return isNaN(num) || trimmed === "" ? trimmed : num;
          }),
        );

      const res = await fetch(`${apiUrl()}/api/office/spreadsheets`, {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify({
          title: sheetTitle.trim(),
          sheets: [{ name: "Varoq1", columns: cols, rows: rows }],
          format: "xlsx",
        }),
      });
      if (res.ok) {
        const art = (await res.json()) as OfficeArtifact;
        setRecentSuccess(art);
        reloadArtifacts();
      } else {
        setError("Jadvalni shakllantirishda xatolik yuz berdi.");
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <PageFrame
      title={m.office?.title ?? "Hujjatlar va Ofis Ustaxonasi"}
      subtitle={
        m.office?.subtitle ??
        "Xavfsiz Word (DOCX) va Excel (XLSX) hujjatlarini yaratish va yuklab olish."
      }
    >
      {/* Safety Notice Banner */}
      <Card className="mb-6 border-line bg-surface-2/40">
        <div className="flex items-center gap-3">
          <div className="rounded-xl bg-success/10 p-2.5 text-success">
            <ShieldCheck size={20} />
          </div>
          <p className="text-xs leading-relaxed text-ink-muted">
            {m.office?.safeNotice ??
              "Xavfsizlik kafolati: Barcha Word va Excel fayllari makroslarsiz, tashqi havfli skriptlarsiz toza formatda generatsiya qilinadi."}
          </p>
        </div>
      </Card>

      {/* Templates Row */}
      <div className="mb-6">
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-muted">
          {m.office?.templates ?? "Tayyor shablonlar"}
        </h3>
        <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2 lg:grid-cols-4">
          {templates.map((tmpl) => (
            <div
              key={tmpl.id}
              onClick={() => applyTemplate(tmpl)}
              className="group cursor-pointer rounded-xl border border-line bg-surface p-3 transition-all hover:border-accent/40"
            >
              <div className="flex items-center justify-between">
                <span className="rounded bg-surface-2 px-1.5 py-0.5 text-[10px] font-bold uppercase text-accent">
                  {tmpl.type}
                </span>
                <span className="text-[10px] text-ink-faint">{tmpl.category}</span>
              </div>
              <p className="mt-2 text-xs font-semibold text-ink group-hover:text-accent">
                {tmpl.title}
              </p>
              <p className="mt-1 line-clamp-2 text-[11px] text-ink-muted">{tmpl.description}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Tabs */}
      <div className="mb-6 flex gap-2 border-b border-line pb-2" role="tablist">
        <button
          type="button"
          onClick={() => {
            setActiveTab("document");
            setRecentSuccess(null);
          }}
          className={cn(
            "flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors",
            activeTab === "document"
              ? "bg-surface-2 text-ink"
              : "text-ink-muted hover:bg-surface-2/60 hover:text-ink",
          )}
        >
          <FileText size={16} />
          {m.office?.createDocument ?? "Word (DOCX)"}
        </button>
        <button
          type="button"
          onClick={() => {
            setActiveTab("spreadsheet");
            setRecentSuccess(null);
          }}
          className={cn(
            "flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors",
            activeTab === "spreadsheet"
              ? "bg-surface-2 text-ink"
              : "text-ink-muted hover:bg-surface-2/60 hover:text-ink",
          )}
        >
          <FileSpreadsheet size={16} />
          {m.office?.createSpreadsheet ?? "Excel (XLSX)"}
        </button>
        <button
          type="button"
          onClick={() => {
            setActiveTab("artifacts");
            setRecentSuccess(null);
          }}
          className={cn(
            "flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors",
            activeTab === "artifacts"
              ? "bg-surface-2 text-ink"
              : "text-ink-muted hover:bg-surface-2/60 hover:text-ink",
          )}
        >
          <TableIcon size={16} />
          {m.office?.myArtifacts ?? "Mening fayllarim"} ({artifacts.length})
        </button>
      </div>

      {/* Creation Success Banner */}
      {recentSuccess ? (
        <Card className="mb-6 border-success/40 bg-success/5">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-3">
              <CheckCircle2 size={24} className="text-success" />
              <div>
                <h4 className="text-sm font-semibold text-ink">{recentSuccess.title} tayyor!</h4>
                <p className="text-xs text-ink-muted">{recentSuccess.filename}</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <a
                href={`${apiUrl()}${recentSuccess.download_url}`}
                download
                className="flex items-center gap-1.5 rounded-lg bg-accent px-3 py-1.5 text-xs font-semibold text-white transition-opacity hover:opacity-90"
              >
                <Download size={14} />
                {recentSuccess.type === "document" ? "DOCX yuklab olish" : "XLSX yuklab olish"}
              </a>
              {recentSuccess.exports["pdf"] ? (
                <a
                  href={`${apiUrl()}${recentSuccess.exports["pdf"]}`}
                  target="_blank"
                  rel="noreferrer"
                  className="flex items-center gap-1.5 rounded-lg border border-line bg-surface px-3 py-1.5 text-xs font-medium text-ink transition-colors hover:border-accent/40"
                >
                  <FileText size={14} />
                  PDF versiya
                </a>
              ) : null}
            </div>
          </div>
        </Card>
      ) : null}

      {error ? <p className="mb-4 text-xs text-danger">{error}</p> : null}

      {activeTab === "document" ? (
        /* DOCX Creator */
        <Card>
          <form onSubmit={handleCreateDocument} className="space-y-4">
            <TextField
              label={m.office?.docTitle ?? "Hujjat nomi"}
              value={docTitle}
              onChange={(e) => setDocTitle(e.target.value)}
              required
            />
            <TextAreaField
              label={m.office?.contentLabel ?? "Matn (Markdown formatida)"}
              value={docMarkdown}
              onChange={(e) => setDocMarkdown(e.target.value)}
              rows={10}
              required
            />
            <div className="flex items-center justify-between pt-2">
              <label className="flex items-center gap-2 text-xs text-ink-muted">
                <input
                  type="checkbox"
                  checked={exportPdf}
                  onChange={(e) => setExportPdf(e.target.checked)}
                  className="rounded border-line"
                />
                {m.office?.exportPdf ?? "PDF nusxasini ham eksport qilish"}
              </label>

              <Button
                type="submit"
                variant="primary"
                disabled={loading}
                icon={<Download size={15} />}
              >
                {m.office?.generate ?? "DOCX yaratish"}
              </Button>
            </div>
          </form>
        </Card>
      ) : activeTab === "spreadsheet" ? (
        /* XLSX Creator */
        <Card>
          <form onSubmit={handleCreateSpreadsheet} className="space-y-4">
            <TextField
              label={m.office?.spreadsheetTitle ?? "Jadval nomi"}
              value={sheetTitle}
              onChange={(e) => setSheetTitle(e.target.value)}
              required
            />
            <TextField
              label={m.office?.columnsLabel ?? "Ustunlar (vergul bilan)"}
              value={columnsStr}
              onChange={(e) => setColumnsStr(e.target.value)}
              required
            />
            <TextAreaField
              label="Qatorlar ma'lumoti (har bir qator yangi satrda, vergul bilan)"
              value={rowsData}
              onChange={(e) => setRowsData(e.target.value)}
              rows={8}
              required
            />
            <div className="flex justify-end pt-2">
              <Button
                type="submit"
                variant="primary"
                disabled={loading}
                icon={<Download size={15} />}
              >
                {m.office?.generate ?? "XLSX yaratish"}
              </Button>
            </div>
          </form>
        </Card>
      ) : (
        /* Artifacts List */
        <div className="space-y-3">
          {artifacts.length === 0 ? (
            <p className="text-sm text-ink-muted">Hozircha ofis fayllari yaratilmagan.</p>
          ) : (
            artifacts.map((art) => (
              <div
                key={art.artifact_id}
                className="flex items-center justify-between rounded-xl border border-line bg-surface p-3.5 transition-colors hover:border-accent/40"
              >
                <div className="flex items-center gap-3">
                  <div className="rounded-lg bg-surface-2 p-2 text-accent">
                    {art.type === "document" ? (
                      <FileText size={20} />
                    ) : art.type === "spreadsheet" ? (
                      <FileSpreadsheet size={20} />
                    ) : (
                      <TableIcon size={20} />
                    )}
                  </div>
                  <div>
                    <h4 className="text-sm font-semibold text-ink">{art.title}</h4>
                    <span className="text-xs text-ink-muted">{art.filename}</span>
                  </div>
                </div>

                <a
                  href={`${apiUrl()}${art.download_url}`}
                  download
                  className="flex items-center gap-1.5 rounded-lg border border-line bg-surface px-3 py-1.5 text-xs font-medium text-ink transition-colors hover:border-accent/40"
                >
                  <Download size={13} />
                  {m.office?.download ?? "Yuklab olish"}
                </a>
              </div>
            ))
          )}
        </div>
      )}
    </PageFrame>
  );
}
