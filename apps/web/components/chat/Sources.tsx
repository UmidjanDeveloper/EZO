"use client";

import type { SourceCitation } from "@ezo/shared";
import { ExternalLink, FileText, Globe } from "lucide-react";
import Link from "next/link";
import { useI18n } from "@/lib/i18n/context";

/** Where an answer's facts came from. Only sources the answer actually cites are listed. */
export function Sources({ citations }: { citations: SourceCitation[] }) {
  const { m } = useI18n();
  if (citations.length === 0) return null;
  return (
    <div className="mt-2" data-testid="message-sources">
      <p className="mb-1 text-xs font-medium uppercase tracking-wider text-ink-faint">{m.sources.title}</p>
      <ol className="flex flex-col gap-1">
        {citations.map((source) => {
          const Icon = source.kind === "file" ? FileText : Globe;
          const meta = [source.location, source.date, source.kind !== "file" ? source.source_name : null]
            .filter(Boolean)
            .join(" · ");
          const body = (
            <>
              <span className="w-5 shrink-0 text-right font-mono text-xs text-accent">[{source.n}]</span>
              <Icon size={13} className="mt-0.5 shrink-0 text-ink-faint" />
              <span className="min-w-0 flex-1">
                <span className="text-ink">{source.title}</span>
                {source.primary ? <span className="ml-1.5 text-xs text-success">· {m.sources.primary}</span> : null}
                {meta ? <span className="block truncate text-xs text-ink-faint">{meta}</span> : null}
              </span>
              {source.url ? <ExternalLink size={12} className="mt-1 shrink-0 text-ink-faint" /> : null}
            </>
          );
          const className = "flex items-start gap-2 rounded-lg px-1.5 py-1 text-sm hover:bg-surface-2";
          return (
            <li key={source.n} title={source.excerpt} data-testid="message-source">
              {source.url ? (
                <a href={source.url} target="_blank" rel="noopener noreferrer" className={className} aria-label={`${m.sources.open}: ${source.title}`}>
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
