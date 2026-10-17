"use client";

import type { ArtifactVersion } from "@ezo/shared";
import { Download } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { saveBlob } from "@/lib/download";
import { useI18n } from "@/lib/i18n/context";

const PREVIEW = /^preview-(\d+)$/;
const MAX_THUMBNAILS = 24;

/** Other formats of a version (PDF, web version, Word…) and, for presentations, slide previews. */
export function VersionExports({ artifactId, version }: { artifactId: string; version: ArtifactVersion }) {
  const { m, f } = useI18n();
  const files = version.exports.filter((e) => !PREVIEW.test(e.name));
  const previews = version.exports
    .filter((e) => PREVIEW.test(e.name))
    .sort((a, b) => Number(PREVIEW.exec(a.name)?.[1]) - Number(PREVIEW.exec(b.name)?.[1]));
  const qa = version.generation_metadata["qa"] as { passed?: boolean; errors?: number } | undefined;
  const names = m.artifacts.exportNames as Record<string, string>;

  async function download(name: string) {
    const { blob, filename } = await api.downloadExport(artifactId, version.version_number, name);
    saveBlob(blob, filename);
  }

  if (!files.length && !previews.length) return null;
  return (
    <div className="mt-3 flex flex-col gap-2" data-testid="artifact-exports">
      {files.length ? (
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-xs text-ink-faint">{m.artifacts.otherFormats}:</span>
          {files.map((file) => (
            <button
              key={file.name}
              type="button"
              onClick={() => void download(file.name)}
              className="inline-flex items-center gap-1 rounded-md border border-line px-2 py-0.5 text-xs hover:bg-surface-2"
              data-testid={`export-${file.name}`}
            >
              <Download size={12} /> {names[file.name] ?? file.name}
            </button>
          ))}
        </div>
      ) : null}
      {qa ? (
        <p className={`text-xs ${qa.passed ? "text-ink-faint" : "text-danger"}`} data-testid="artifact-qa">
          {qa.passed ? m.artifacts.qaPassed : f(m.artifacts.qaIssues, { n: qa.errors ?? 0 })}
        </p>
      ) : null}
      {previews.length ? (
        <SlideThumbnails
          artifactId={artifactId}
          version={version.version_number}
          names={previews.slice(0, MAX_THUMBNAILS).map((p) => p.name)}
        />
      ) : null}
    </div>
  );
}

function SlideThumbnails({ artifactId, version, names }: { artifactId: string; version: number; names: string[] }) {
  const { m, f } = useI18n();
  const [urls, setUrls] = useState<string[]>([]);
  const key = names.join(",");

  useEffect(() => {
    let cancelled = false;
    const created: string[] = [];
    void (async () => {
      for (const name of key.split(",")) {
        try {
          const { blob } = await api.downloadExport(artifactId, version, name);
          if (cancelled) return;
          const url = URL.createObjectURL(blob);
          created.push(url);
          setUrls((current) => [...current, url]);
        } catch {
          return; // a missing preview is not worth an error message; the files remain downloadable
        }
      }
    })();
    return () => {
      cancelled = true;
      created.forEach((url) => URL.revokeObjectURL(url));
      setUrls([]);
    };
  }, [artifactId, version, key]);

  return (
    <div>
      <p className="mb-1 text-xs text-ink-faint">{m.artifacts.slides}</p>
      <div className="grid grid-cols-3 gap-1.5 sm:grid-cols-4" data-testid="slide-previews">
        {urls.map((url, index) => (
          // eslint-disable-next-line @next/next/no-img-element -- local blob URLs, no optimisation needed
          <img
            key={url}
            src={url}
            alt={f(m.artifacts.slidePreview, { n: index + 1 })}
            className="aspect-video w-full rounded border border-line object-cover"
          />
        ))}
      </div>
    </div>
  );
}
