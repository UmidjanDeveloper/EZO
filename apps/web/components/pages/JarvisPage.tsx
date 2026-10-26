"use client";

import { Button, Card, cn, Spinner } from "@ezo/ui";
import { AlertTriangle, Plus, RefreshCw, ShieldAlert, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { fetchCapabilities, JarvisApiError, postPercentages } from "@/lib/jarvis-api";
import {
  buildPercentageRequest,
  featureState,
  MAX_PAIRS,
  receiptShowsNoDelivery,
  type Capabilities,
  type PercentageMethod,
  type PercentageResult,
  type PercentageRowInput,
} from "@/lib/jarvis-contract";
import { useI18n } from "@/lib/i18n/context";
import { JarvisConsole } from "@/components/jarvis/JarvisConsole";
import { PageFrame } from "./PageFrame";

type CapabilityState =
  | { status: "loading" }
  | { status: "ready"; capabilities: Capabilities }
  | { status: "error"; httpStatus: number | null; code: string };

const FEATURE_LABEL_KEYS = {
  windows_downloads: "featureWindowsDownloads",
  chrome_actions: "featureChromeActions",
  mobile_actions: "featureMobileActions",
  office_pdf: "featureOfficePdf",
  telegram_send: "featureTelegramSend",
} as const;

const INPUT_CLASS =
  "w-full rounded-lg border border-line bg-surface-raised px-3 py-2 text-sm text-ink outline-none focus:border-accent focus:ring-1 focus:ring-accent";

/**
 * JARVIS page: capability inspection, the governed task console (device pairing,
 * Telegram recipients, tasks, exact-action approvals) and the percentage calculator.
 * Every state shown comes from a validated backend response; "delivered" appears only
 * with Telegram's own message id recorded by the API.
 */
export function JarvisPage() {
  const { m } = useI18n();
  const t = m.jarvis;
  const [state, setState] = useState<CapabilityState>({ status: "loading" });
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let alive = true;
    fetchCapabilities()
      .then((capabilities) => alive && setState({ status: "ready", capabilities }))
      .catch((error: unknown) => {
        if (!alive) return;
        if (error instanceof JarvisApiError) setState({ status: "error", httpStatus: error.status, code: error.code });
        else setState({ status: "error", httpStatus: null, code: "network_error" });
      });
    return () => {
      alive = false;
    };
  }, [reloadKey]);

  const reload = () => {
    setState({ status: "loading" });
    setReloadKey((key) => key + 1);
  };

  return (
    <PageFrame
      title={t.title}
      subtitle={t.subtitle}
      actions={
        <Button variant="secondary" size="sm" onClick={reload} disabled={state.status === "loading"} data-testid="jarvis-refresh">
          <RefreshCw className={cn("mr-1.5 h-3.5 w-3.5", state.status === "loading" && "animate-spin")} />
          {t.refresh}
        </Button>
      }
    >
      <div className="space-y-6">
        <section aria-labelledby="jarvis-features-title" data-testid="jarvis-features">
          <Card className="p-5">
            <h2 id="jarvis-features-title" className="mb-3 text-sm font-semibold text-ink">
              {t.featuresTitle}
            </h2>
            <FeatureList state={state} />
          </Card>
        </section>

        <JarvisConsole />

        <PercentageCalculator />
      </div>
    </PageFrame>
  );
}

function FeatureList({ state }: { state: CapabilityState }) {
  const { m } = useI18n();
  const t = m.jarvis;
  if (state.status === "loading") {
    return (
      <p className="flex items-center gap-2 text-sm text-ink-muted" data-testid="jarvis-loading">
        <Spinner className="h-4 w-4" /> {t.loading}
      </p>
    );
  }
  if (state.status === "error") {
    const unauthorized = state.httpStatus === 401 || state.httpStatus === 403;
    return (
      <p className="flex items-start gap-2 text-sm text-rose-500" role="alert" data-testid="jarvis-load-error">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
        <span>{unauthorized ? t.signInRequired : t.loadFailed}</span>
      </p>
    );
  }
  const entries = Object.entries(state.capabilities.device_features);
  return (
    <ul className="space-y-2">
      {entries.map(([name, feature]) => {
        const label =
          name in FEATURE_LABEL_KEYS ? t[FEATURE_LABEL_KEYS[name as keyof typeof FEATURE_LABEL_KEYS]] : name;
        const feat = featureState(feature);
        const description =
          feat === "not_available"
            ? t.notAvailable
            : feat === "authorized_by_backend"
              ? t.authorizedByBackend
              : t.reportedNotAuthorized;
        return (
          <li
            key={name}
            data-testid={`jarvis-feature-${name}`}
            data-state={feat}
            className="rounded-lg border border-line bg-surface-raised/50 p-3 text-sm"
          >
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="font-medium text-ink">{label}</span>
              <span
                className={cn(
                  "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium",
                  feat === "authorized_by_backend" ? "bg-emerald-500/10 text-emerald-500" : "bg-amber-500/10 text-amber-500",
                )}
              >
                <ShieldAlert className="h-3 w-3" aria-hidden />
                {description}
              </span>
            </div>
            {feature.missing_prerequisites.length > 0 ? (
              <p className="mt-1.5 text-xs text-ink-muted">
                {t.prerequisitesLabel}:{" "}
                {feature.missing_prerequisites.map((code) => (
                  <code key={code} className="mr-1 rounded bg-surface px-1 py-0.5 font-mono text-[11px]">
                    {code}
                  </code>
                ))}
              </p>
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}

function PercentageCalculator() {
  const { m } = useI18n();
  const t = m.jarvis;
  const [method, setMethod] = useState<PercentageMethod>("percent_change");
  const [decimals, setDecimals] = useState(2);
  const [rows, setRows] = useState<PercentageRowInput[]>([{ previous: "", current: "" }]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<PercentageResult | null>(null);

  const updateRow = (index: number, patch: Partial<PercentageRowInput>) =>
    setRows((current) => current.map((row, i) => (i === index ? { ...row, ...patch } : row)));

  const submit = async () => {
    setError(null);
    setResult(null);
    const built = buildPercentageRequest(method, rows, decimals);
    if (!built.ok) {
      setError(t.errValidation);
      return;
    }
    setBusy(true);
    try {
      setResult(await postPercentages(built.body));
    } catch (e) {
      if (e instanceof JarvisApiError && e.code === "unexpected_response_shape") setError(t.errShape);
      else if (e instanceof JarvisApiError) setError(`${t.errRequest} (${e.status}: ${e.code})`);
      else setError(t.errRequest);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section aria-labelledby="jarvis-calc-title" data-testid="jarvis-calc">
      <Card className="p-5">
        <h2 id="jarvis-calc-title" className="text-sm font-semibold text-ink">
          {t.calcTitle}
        </h2>
        <p className="mt-1 text-xs text-ink-muted">{t.calcNote}</p>

        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <label className="text-xs text-ink-muted">
            {t.method}
            <select
              className={cn(INPUT_CLASS, "mt-1")}
              value={method}
              onChange={(e) => setMethod(e.target.value as PercentageMethod)}
              data-testid="jarvis-method"
            >
              <option value="percent_change">{t.methodChange}</option>
              <option value="percent_of">{t.methodOf}</option>
            </select>
          </label>
          <label className="text-xs text-ink-muted">
            {t.decimals}
            <input
              type="number"
              min={0}
              max={8}
              step={1}
              className={cn(INPUT_CLASS, "mt-1")}
              value={decimals}
              onChange={(e) => setDecimals(Number(e.target.value))}
              data-testid="jarvis-decimals"
            />
          </label>
        </div>

        <div className="mt-3 space-y-2">
          {rows.map((row, index) => (
            <div key={index} className="grid grid-cols-[1fr_1fr_auto] items-end gap-2">
              <label className="text-xs text-ink-muted">
                {t.previous}
                <input
                  inputMode="decimal"
                  className={cn(INPUT_CLASS, "mt-1")}
                  value={row.previous}
                  onChange={(e) => updateRow(index, { previous: e.target.value })}
                  data-testid={`jarvis-previous-${index}`}
                />
              </label>
              <label className="text-xs text-ink-muted">
                {t.current}
                <input
                  inputMode="decimal"
                  className={cn(INPUT_CLASS, "mt-1")}
                  value={row.current}
                  onChange={(e) => updateRow(index, { current: e.target.value })}
                  data-testid={`jarvis-current-${index}`}
                />
              </label>
              <Button
                variant="secondary"
                size="sm"
                aria-label={t.removeRow}
                disabled={rows.length === 1}
                onClick={() => setRows((current) => current.filter((_, i) => i !== index))}
              >
                <Trash2 className="h-3.5 w-3.5" />
              </Button>
            </div>
          ))}
        </div>

        <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
          <Button
            variant="secondary"
            size="sm"
            disabled={rows.length >= MAX_PAIRS}
            onClick={() => setRows((current) => [...current, { previous: "", current: "" }])}
            data-testid="jarvis-add-row"
          >
            <Plus className="mr-1 h-3.5 w-3.5" />
            {t.addRow}
          </Button>
          <Button variant="primary" size="sm" onClick={() => void submit()} disabled={busy} data-testid="jarvis-calculate">
            {busy ? t.calculating : t.calculate}
          </Button>
        </div>

        {error ? (
          <p className="mt-3 flex items-start gap-2 text-xs text-rose-500" role="alert" data-testid="jarvis-calc-error">
            <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
            {error}
          </p>
        ) : null}

        {result ? <CalculationResult result={result} /> : null}
      </Card>
    </section>
  );
}

function CalculationResult({ result }: { result: PercentageResult }) {
  const { m } = useI18n();
  const t = m.jarvis;
  const { receipt } = result;
  return (
    <div className="mt-4 space-y-3" data-testid="jarvis-result">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-ink-muted">{t.result}</h3>
      <table className="w-full text-left text-xs">
        <thead>
          <tr className="border-b border-line text-ink-muted">
            <th className="pb-1.5 font-medium">{t.previous}</th>
            <th className="pb-1.5 font-medium">{t.current}</th>
            <th className="pb-1.5 font-medium">%</th>
          </tr>
        </thead>
        <tbody>
          {result.results.map((row) => (
            <tr key={row.id} className="border-b border-line/40">
              <td className="py-1.5 font-mono">{row.previous}</td>
              <td className="py-1.5 font-mono">{row.current}</td>
              <td className="py-1.5 font-mono font-semibold" data-testid="jarvis-result-percent">
                {row.result_percent}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="text-[11px] text-ink-muted">
        <code className="font-mono">{result.formula}</code> · {result.rounding} · {result.provenance}
      </p>
      <div className="rounded-lg border border-line bg-surface-raised/50 p-3 text-xs" data-testid="jarvis-receipt">
        <p className="font-medium text-ink">{t.receiptTitle}</p>
        <p className="mt-1 break-all font-mono text-[11px] text-ink-muted">{receipt.id}</p>
        <p className="mt-1 text-ink-muted">
          {receiptShowsNoDelivery(receipt) ? t.receiptNote : `${receipt.outcome} / ${receipt.external_delivery}`}
        </p>
      </div>
    </div>
  );
}
