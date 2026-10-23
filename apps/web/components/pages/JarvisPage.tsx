"use client";

import { Button, Card, Spinner } from "@ezo/ui";
import { CheckCircle2, ShieldAlert, XCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { apiUrl, storedToken } from "@/lib/api";
import { PageFrame } from "./PageFrame";

/**
 * JARVIS Mode — only what the backend actually does today (routes in
 * apps/api/src/ezo_api/api/routes/jarvis.py):
 *   GET  /api/jarvis/capabilities   real tool registry + device feature prerequisites
 *   POST /api/jarvis/percentages    exact decimal arithmetic with an owner-scoped receipt
 *   GET  /api/jarvis/receipts/{id}  the stored receipt
 * No device is paired, no file is opened and no message is sent from this page:
 * those features report their missing prerequisites instead of a simulated success.
 */

interface Availability {
  available: boolean;
  missing_prerequisites: string[];
  execution_authorized: boolean;
}

interface Capabilities {
  tools: { name: string; description: string; requires_confirmation: boolean }[];
  device_features: Record<string, Availability>;
}

interface PercentageResult {
  method: string;
  formula: string;
  results: { id: string; previous: string; current: string; result_percent: string }[];
  receipt: { id: string; outcome: string; external_delivery: string };
}

const FEATURE_LABELS: Record<string, string> = {
  windows_downloads: "Windows: Downloads papkasidagi fayllar",
  chrome_actions: "Chrome kengaytmasi amallari",
  mobile_actions: "Telefon amallari",
  office_pdf: "Hujjatni PDF'ga aylantirish (izolyatsiyalangan worker)",
  telegram_send: "Telegram orqali yuborish",
};

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const token = storedToken.get().trim();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(`${apiUrl()}/api/jarvis/${path}`, { ...init, headers, cache: "no-store" });
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = body?.detail;
    throw new Error(
      (typeof detail === "string" ? detail : detail?.message ?? detail?.code) ?? `So‘rov bajarilmadi (${response.status}).`,
    );
  }
  return body as T;
}

function parsePairs(text: string) {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line, index) => {
      const [previous, current] = line.split(/[\s,;]+/);
      return { id: `q${index + 1}`, previous, current };
    });
}

export function JarvisPage() {
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null);
  const [loadError, setLoadError] = useState("");
  const [method, setMethod] = useState<"percent_change" | "percent_of">("percent_change");
  const [pairsText, setPairsText] = useState("");
  const [result, setResult] = useState<PercentageResult | null>(null);
  const [calcError, setCalcError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let active = true;
    request<Capabilities>("capabilities")
      .then((data) => active && setCapabilities(data))
      .catch((e: unknown) => active && setLoadError(e instanceof Error ? e.message : String(e)));
    return () => {
      active = false;
    };
  }, []);

  async function calculate() {
    setBusy(true);
    setCalcError("");
    setResult(null);
    try {
      setResult(
        await request<PercentageResult>("percentages", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ method, pairs: parsePairs(pairsText), decimal_places: 2 }),
        }),
      );
    } catch (e) {
      setCalcError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <PageFrame
      title="JARVIS rejimi"
      subtitle="Qurilma va xabar amallari hali ulanmagan. Bu sahifa faqat haqiqatda ishlaydigan qismlarni ko‘rsatadi."
    >
      <div className="grid gap-6">
        <Card className="p-5">
          <h2 className="flex items-center gap-2 font-semibold text-ink">
            <ShieldAlert className="h-4 w-4 text-amber-500" aria-hidden />
            Qurilma amallari holati
          </h2>
          <p className="mt-1 text-sm text-ink-muted">
            Ovozli buyruq bilan fayl ochish, PDF tayyorlash va Telegram’da yuborish hali amalga oshirilmagan. Har bir
            amal uchun yetishmayotgan shartlar backend’dan olinadi.
          </p>
          {loadError && (
            <p role="alert" className="mt-3 text-sm text-danger">
              Backend bilan bog‘lanib bo‘lmadi: {loadError}
            </p>
          )}
          {!capabilities && !loadError && <Spinner className="mt-3" />}
          {capabilities && (
            <ul className="mt-3 grid gap-2">
              {Object.entries(capabilities.device_features).map(([name, state]) => (
                <li key={name} className="flex items-start gap-2 rounded-lg border border-line p-3 text-sm">
                  {state.available ? (
                    <CheckCircle2 className="mt-0.5 h-4 w-4 text-success" aria-hidden />
                  ) : (
                    <XCircle className="mt-0.5 h-4 w-4 text-danger" aria-hidden />
                  )}
                  <span>
                    <span className="font-medium text-ink">{FEATURE_LABELS[name] ?? name}</span>
                    <span className="block text-xs text-ink-muted">
                      {state.available ? "Mavjud" : `Mavjud emas — kerak: ${state.missing_prerequisites.join(", ")}`}
                    </span>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card className="p-5">
          <h2 className="font-semibold text-ink">Foiz hisoblash (aniq o‘nlik arifmetika)</h2>
          <p className="mt-1 text-sm text-ink-muted">
            Har qatorga ikkita son kiriting: oldingi va joriy qiymat. Qiymatlarni o‘zingiz kiritasiz; hujjatdan avtomatik
            o‘qish hali yo‘q. Natija va kvitansiya serverda saqlanadi.
          </p>
          <div className="mt-3 grid gap-3">
            <label className="text-sm text-ink">
              Usul{" "}
              <select
                className="ml-2 rounded-lg border border-line bg-surface-2 px-2 py-1"
                value={method}
                onChange={(e) => setMethod(e.target.value as typeof method)}
              >
                <option value="percent_change">O‘zgarish foizi: (joriy − oldingi) / oldingi × 100</option>
                <option value="percent_of">Ulush: joriy / oldingi × 100</option>
              </select>
            </label>
            <textarea
              aria-label="Oldingi va joriy qiymatlar"
              className="min-h-24 rounded-lg border border-line bg-surface-2 p-3 font-mono text-sm"
              placeholder={"1200 1500\n80 72"}
              value={pairsText}
              onChange={(e) => setPairsText(e.target.value)}
            />
            <div>
              <Button onClick={() => void calculate()} disabled={busy || !pairsText.trim()}>
                {busy ? "Hisoblanmoqda…" : "Hisoblash"}
              </Button>
            </div>
            {calcError && (
              <p role="alert" className="text-sm text-danger">
                {calcError}
              </p>
            )}
            {result && (
              <div aria-live="polite" className="grid gap-2 text-sm">
                <p className="text-xs text-ink-muted">Formula: {result.formula}</p>
                <table className="w-full text-left">
                  <thead>
                    <tr className="text-xs text-ink-muted">
                      <th>Qator</th>
                      <th>Oldingi</th>
                      <th>Joriy</th>
                      <th>Natija</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.results.map((row) => (
                      <tr key={row.id}>
                        <td>{row.id}</td>
                        <td>{row.previous}</td>
                        <td>{row.current}</td>
                        <td className="font-semibold">{row.result_percent}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="text-xs text-ink-muted">
                  Kvitansiya: <code>{result.receipt.id}</code> — hisoblash bajarildi; tashqi yuborish urinilmadi.
                </p>
              </div>
            )}
          </div>
        </Card>

        {capabilities && (
          <Card className="p-5">
            <h2 className="font-semibold text-ink">Ro‘yxatdan o‘tgan vositalar</h2>
            <p className="mt-1 text-xs text-ink-muted">
              Bu ro‘yxat vosita ma’lumoti; u biror amalni bajarishga ruxsat bermaydi.
            </p>
            <ul className="mt-3 grid gap-1 text-sm">
              {capabilities.tools.map((tool) => (
                <li key={tool.name}>
                  <code className="text-accent">{tool.name}</code>
                  <span className="text-ink-muted"> — {tool.description}</span>
                </li>
              ))}
            </ul>
          </Card>
        )}
      </div>
    </PageFrame>
  );
}
