"use client";

import type { ArtifactRef } from "@ezo/shared";
import { Download, ExternalLink } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { api } from "@/lib/api";
import { saveBlob } from "@/lib/download";
import { useI18n } from "@/lib/i18n/context";
import { ArtifactIcon } from "./ArtifactIcon";

/** An artifact created in a conversation, shown under the answer. */
export function ArtifactCard({ artifact }: { artifact: ArtifactRef }) {
  const { m, f } = useI18n();
  const [busy, setBusy] = useState(false);
  const typeLabel = m.artifacts.types[artifact.type as keyof typeof m.artifacts.types] ?? artifact.type;

  async function download() {
    setBusy(true);
    try {
      const detail = await api.getArtifact(artifact.id);
      const version = detail.current_version?.version_number ?? artifact.version;
      const { blob, filename } = await api.downloadArtifact(artifact.id, version);
      saveBlob(blob, filename);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className="mt-2 flex max-w-md items-center gap-3 rounded-xl border border-line bg-surface px-3 py-2"
      data-testid="artifact-card"
    >
      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-accent/10 text-accent">
        <ArtifactIcon type={artifact.type} size={18} />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm font-medium">{artifact.title}</span>
        <span className="block text-xs text-ink-faint">
          {typeLabel} · {f(m.artifacts.version, { n: artifact.version })}
        </span>
      </span>
      <button
        type="button"
        onClick={() => void download()}
        disabled={busy}
        className="rounded p-1.5 text-ink-faint hover:text-ink disabled:opacity-50"
        aria-label={m.artifacts.download}
        title={m.artifacts.download}
      >
        <Download size={16} />
      </button>
      <Link
        href={`/artifacts?open=${artifact.id}`}
        className="rounded p-1.5 text-ink-faint hover:text-ink"
        aria-label={m.artifacts.open}
        title={m.artifacts.open}
      >
        <ExternalLink size={16} />
      </Link>
    </div>
  );
}
