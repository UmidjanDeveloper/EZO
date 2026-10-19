"use client";

import type { SourceCitation } from "@ezo/shared";
import { AlertCircle, CheckCircle2, Clock, ExternalLink, FileText, Globe, Scale, Tag } from "lucide-react";
import Link from "next/link";
import { useI18n } from "@/lib/i18n/context";

/** Where an answer's facts came from. Only sources the answer actually cites are listed. */
export function Sources({ citations }: { citations: SourceCitation[] }) {
  const { m, f } = useI18n();
  if (citations.length === 0) return null;

  return (
    <div className="mt-2" data-testid="message-sources">
      <p className="mb-1 text-xs font-medium uppercase tracking-wider text-ink-faint">{m.sources.title}</p>
      <ol className="flex flex-col gap-1.5">
        {citations.map((source) => {
          const Icon = source.kind === "file" ? FileText : Globe;
          const metaItems = [
            source.location,
            source.date,
            source.kind !== "file" ? source.source_name : null,
          ].filter(Boolean);

          const freshness = source.freshness_status;
          const freshnessLabel =
            freshness === "changed"
              ? m.sources.freshness.changed
              : freshness === "not_recently_checked"
                ? m.sources.freshness.notRecentlyChecked
                : freshness === "current"
                  ? m.sources.freshness.current
                  : null;

          const lastChecked = source.last_checked_at
            ? f(m.sources.lastChecked, { d: new Date(source.last_checked_at).toLocaleDateString() })
            : null;

          const body = (
            <div className="flex w-full items-start gap-2">
              <span className="w-5 shrink-0 text-right font-mono text-xs text-accent">[{source.n}]</span>
              <Icon size={14} className="mt-0.5 shrink-0 text-ink-faint" />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="font-medium text-ink">{source.title}</span>
                  {source.primary ? (
                    <span className="rounded bg-success/10 px-1 py-0.2 text-[11px] font-medium text-success">
                      {m.sources.primary}
                    </span>
                  ) : null}
                  {freshnessLabel ? (
                    <span
                      data-testid="freshness-badge"
                      className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] font-medium ${
                        freshness === "changed"
                          ? "bg-warning/15 text-warning border border-warning/30"
                          : freshness === "not_recently_checked"
                            ? "bg-ink-faint/10 text-ink-muted border border-ink-faint/20"
                            : "bg-success/10 text-success border border-success/20"
                      }`}
                      title={source.freshness_note || freshnessLabel}
                    >
                      {freshness === "changed" ? (
                        <AlertCircle size={10} className="shrink-0" />
                      ) : freshness === "not_recently_checked" ? (
                        <Clock size={10} className="shrink-0" />
                      ) : (
                        <CheckCircle2 size={10} className="shrink-0" />
                      )}
                      {freshnessLabel}
                    </span>
                  ) : null}
                </div>

                {/* Provenance: version, license, last-checked timestamp */}
                <div className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-ink-muted">
                  {metaItems.length > 0 ? <span>{metaItems.join(" · ")}</span> : null}
                  {source.version ? (
                    <span className="inline-flex items-center gap-0.5">
                      <Tag size={11} className="text-ink-faint" />
                      {f(m.sources.version, { v: source.version })}
                    </span>
                  ) : null}
                  {source.license ? (
                    <span className="inline-flex items-center gap-0.5">
                      <Scale size={11} className="text-ink-faint" />
                      {f(m.sources.license, { l: source.license })}
                    </span>
                  ) : null}
                  {lastChecked ? (
                    <span className="text-[11px] text-ink-faint">{lastChecked}</span>
                  ) : null}
                </div>
              </div>
              {source.url ? <ExternalLink size={12} className="mt-1 shrink-0 text-ink-faint" /> : null}
            </div>
          );
          const className = "flex items-start rounded-lg px-2 py-1.5 text-sm hover:bg-surface-2 transition-colors";
          return (
            <li key={source.n} title={source.excerpt} data-testid="message-source">
              {source.url ? (
                <a
                  href={source.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className={className}
                  aria-label={`${m.sources.open}: ${source.title}`}
                >
                  {body}
                </a>
              ) : (
                <Link href="/knowledge" className={className}>
                  {body}
                </Link>
              )}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
