"use client";

import type { ArtifactVersion } from "@ezo/shared";
import { Download } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { saveBlob } from "@/lib/download";
import { useI18n } from "@/lib/i18n/context";

const PREVIEW = /^preview-(\d+)$/;
const MAX_THUMBNAILS = 24;

export interface ImageInfo {
  placeholder: boolean;
  /** "provider · model" of a generated picture, "EZO" for diagrams, null if unknown. */
  madeBy: string | null;
}

/** How an image version was made, from its generation metadata. */
export function imageInfo(meta: Record<string, unknown>): ImageInfo {
  const placeholder = meta["placeholder"] === true;
  if (meta["kind"] === "diagram") return { placeholder: false, madeBy: "EZO" };
  const provider = typeof meta["provider"] === "string" ? meta["provider"] : null;
  const model = typeof meta["model"] === "string" ? meta["model"] : null;
  if (placeholder || !provider) return { placeholder, madeBy: null };
  return { placeholder, madeBy: model ? `${provider} · ${model}` : provider };
}

/** Other formats of a version (PDF, web version, Word…), slide previews, or an image preview. */
export function VersionExports({
  artifactId,
  version,
  artifactType,
}: {
  artifactId: string;
  version: ArtifactVersion;
  artifactType?: string;
}) {
  const { m, f } = useI18n();
  const isImage = artifactType === "image";
  const info = isImage ? imageInfo(version.generation_metadata) : null;
  const files = version.exports.filter((e) => !PREVIEW.test(e.name));
  const previews = version.exports
    .filter((e) => PREVIEW.test(e.name))
    .sort((a, b) => Number(PREVIEW.exec(a.name)?.[1]) - Number(PREVIEW.exec(b.name)?.[1]));
  const qa = version.generation_metadata["qa"] as { passed?: boolean; errors?: number } | undefined;
  const names = m.artifacts.exportNames as Record<string, string>;
  const site = version.exports.find((e) => e.name === "site");
  const projectFiles = projectFileList(version.generation_metadata);

  async function download(name: string) {
    const { blob, filename } = await api.downloadExport(artifactId, version.version_number, name);
    saveBlob(blob, filename);
  }

  if (!files.length && !previews.length && !projectFiles.length) return null;
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
      {projectFiles.length ? (
        <details className="text-xs" data-testid="project-files">
          <summary className="cursor-pointer text-ink-faint">
            {f(m.artifacts.projectFiles, { n: projectFiles.length })}
          </summary>
          <ul className="mt-1 grid gap-0.5 font-mono text-ink-soft sm:grid-cols-2">
            {projectFiles.map((path) => (
              <li key={path}>{path}</li>
            ))}
          </ul>
          <p className="mt-1 text-ink-faint">{m.artifacts.notRun}</p>
        </details>
      ) : null}
      {site ? <SitePreview artifactId={artifactId} version={version.version_number} /> : null}
      {info && (info.placeholder || info.madeBy) ? (
        <p className={`text-xs ${info.placeholder ? "text-danger" : "text-ink-faint"}`} data-testid="image-origin">
          {info.placeholder ? m.artifacts.placeholder : f(m.artifacts.madeBy, { who: info.madeBy ?? "" })}
        </p>
      ) : null}
      {previews.length ? (
        <SlideThumbnails
          artifactId={artifactId}
          version={version.version_number}
          names={previews.slice(0, MAX_THUMBNAILS).map((p) => p.name)}
          single={isImage}
        />
      ) : null}
    </div>
  );
}

/** Paths of a project built by the Developer Agent ([] for any other artifact). */
export function projectFileList(meta: Record<string, unknown>): string[] {
  const files = meta["files"];
  if (!Array.isArray(files)) return [];
  return files
    .map((file) => (file && typeof file === "object" ? (file as { path?: unknown }).path : null))
    .filter((path): path is string => typeof path === "string")
    .slice(0, 60);
}

/**
 * A built website, shown in a frame that may not run scripts, submit forms or reach this
 * page (an empty sandbox gives it an opaque origin): generated code never runs with the
 * owner's session. The downloadable one-file version runs fully in the user's own browser.
 */
function SitePreview({ artifactId, version }: { artifactId: string; version: number }) {
  const { m } = useI18n();
  const [html, setHtml] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const { blob } = await api.downloadExport(artifactId, version, "site");
        const text = await blob.text();
        if (!cancelled) setHtml(text);
      } catch {
        // The file stays downloadable; a missing preview needs no error message.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [artifactId, version]);

  if (html === null) return null;
  return (
    <div>
      <p className="mb-1 text-xs text-ink-faint">{m.artifacts.sitePreview}</p>
      <iframe
        title={m.artifacts.preview}
        sandbox=""
        srcDoc={html}
        referrerPolicy="no-referrer"
        className="h-96 w-full rounded-lg border border-line bg-white"
        data-testid="site-preview"
      />
    </div>
  );
}

function SlideThumbnails({
  artifactId,
  version,
  names,
  single = false,
}: {
  artifactId: string;
  version: number;
  names: string[];
  single?: boolean;
}) {
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

  if (single) {
    return urls[0] ? (
      // eslint-disable-next-line @next/next/no-img-element -- local blob URL
      <img
        src={urls[0]}
        alt={m.artifacts.preview}
        className="max-h-96 max-w-full rounded-lg border border-line object-contain"
        data-testid="image-preview"
      />
    ) : null;
  }
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
