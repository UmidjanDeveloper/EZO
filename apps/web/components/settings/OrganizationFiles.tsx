"use client";

import type { OrganizationFile, OrganizationProfile, WritingDocumentType } from "@ezo/shared";
import { Button, SelectField, Spinner } from "@ezo/ui";
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { formatBytes, saveBlob } from "@/lib/download";
import { useI18n } from "@/lib/i18n/context";
import { useApiData } from "@/lib/use-api-data";

/** Logo, approved Word templates and example documents of an organization profile. */
export function OrganizationFiles({
  profile,
  onProfile,
}: {
  profile: OrganizationProfile;
  onProfile: (next: OrganizationProfile) => void;
}) {
  const { m, language: lang, f } = useI18n();
  const t = m.organization;
  const { data: types } = useApiData(useCallback(() => api.documentTypes(), []));
  const [files, setFiles] = useState<OrganizationFile[] | null>(null);
  const [logoUrl, setLogoUrl] = useState<string | null>(null);
  const [docType, setDocType] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const logoInput = useRef<HTMLInputElement>(null);
  const templateInput = useRef<HTMLInputElement>(null);
  const exampleInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let cancelled = false;
    void api
      .organizationFiles(profile.id)
      .then((list) => !cancelled && setFiles(list))
      .catch((reason: Error) => !cancelled && setMessage(reason.message));
    return () => {
      cancelled = true;
    };
  }, [profile.id]);

  useEffect(() => {
    if (!profile.has_logo) return;
    let cancelled = false;
    let created: string | null = null;
    void api
      .organizationLogo(profile.id)
      .then(({ blob }) => {
        if (cancelled) return;
        created = URL.createObjectURL(blob);
        setLogoUrl(created);
      })
      .catch(() => undefined); // no preview: the logo can still be replaced or removed
    return () => {
      cancelled = true;
      if (created) URL.revokeObjectURL(created);
    };
  }, [profile.id, profile.has_logo]);

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setMessage(null);
    try {
      await action();
    } catch (reason) {
      setMessage((reason as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const official = (types ?? []).filter((type: WritingDocumentType) => type.draft);
  const typeName = (key: string | null) => {
    if (!key) return t.anyType;
    const type = types?.find((item) => item.key === key);
    return type ? (type.names[lang] ?? type.names.uz ?? key) : key;
  };

  function upload(kind: OrganizationFile["kind"], list: FileList | null) {
    const file = list?.[0];
    if (!file) return;
    void run(async () => {
      const added = await api.uploadOrganizationFile(profile.id, file, file.name, kind, { docType: docType || null });
      setFiles((current) => [added, ...(current ?? [])]);
      setMessage(kind === "template" && added.has_marker === false ? t.noMarker : m.common.saved);
    });
  }

  function remove(file: OrganizationFile) {
    if (!window.confirm(f(t.confirmFileDelete, { name: file.title }))) return;
    void run(async () => {
      await api.deleteOrganizationFile(profile.id, file.id);
      setFiles((current) => (current ?? []).filter((item) => item.id !== file.id));
    });
  }

  const section = (kind: OrganizationFile["kind"]) => {
    const items = (files ?? []).filter((file) => file.kind === kind);
    if (files === null) return <p className="text-sm text-ink-faint">{t.loading}</p>;
    if (!items.length) return <p className="text-sm text-ink-faint">{t.noFiles}</p>;
    return (
      <ul className="divide-y divide-line rounded-lg border border-line">
        {items.map((file) => (
          <li key={file.id} className="flex flex-wrap items-center gap-2 px-3 py-2 text-sm" data-testid={`org-${kind}`}>
            <span className="min-w-0 flex-1 truncate font-medium">{file.title}</span>
            <span className="text-xs text-ink-faint">
              {typeName(file.doc_type)} · {formatBytes(file.size_bytes)}
            </span>
            <Button
              variant="ghost"
              onClick={() =>
                void run(async () => {
                  const { blob, filename } = await api.downloadOrganizationFile(profile.id, file.id);
                  saveBlob(blob, filename);
                })
              }
              disabled={busy}
            >
              {t.download}
            </Button>
            <Button variant="ghost" onClick={() => remove(file)} disabled={busy}>
              {t.remove}
            </Button>
          </li>
        ))}
      </ul>
    );
  };

  return (
    <div className="mt-6 grid gap-5 border-t border-line pt-5" data-testid="organization-files">
      <section>
        <h3 className="mb-1 text-sm font-medium">{t.logo}</h3>
        <p className="mb-2 text-xs text-ink-faint">{t.logoHint}</p>
        <div className="flex flex-wrap items-center gap-3">
          {profile.has_logo && logoUrl ? (
            // eslint-disable-next-line @next/next/no-img-element -- a local blob preview
            <img src={logoUrl} alt={t.logo} className="h-14 w-14 rounded border border-line object-contain" data-testid="org-logo" />
          ) : (
            <span className="text-sm text-ink-faint">{t.noLogo}</span>
          )}
          <Button variant="secondary" onClick={() => logoInput.current?.click()} disabled={busy}>
            {profile.has_logo ? t.replaceLogo : t.addLogo}
          </Button>
          {profile.has_logo ? (
            <Button
              variant="ghost"
              disabled={busy}
              onClick={() =>
                void run(async () => {
                  await api.deleteOrganizationLogo(profile.id);
                  onProfile({ ...profile, has_logo: false });
                })
              }
            >
              {t.remove}
            </Button>
          ) : null}
          <input
            ref={logoInput}
            type="file"
            accept="image/png,image/jpeg,image/webp"
            className="sr-only"
            data-testid="org-logo-input"
            onChange={(event) => {
              const file = event.target.files?.[0];
              event.target.value = "";
              if (file) void run(async () => onProfile(await api.uploadOrganizationLogo(profile.id, file, file.name)));
            }}
          />
        </div>
      </section>

      <section>
        <h3 className="mb-1 text-sm font-medium">{t.templates}</h3>
        <p className="mb-2 text-xs text-ink-faint">{t.templatesHint}</p>
        <div className="mb-3 flex flex-wrap items-end gap-2">
          <SelectField label={t.forType} value={docType} onChange={(event) => setDocType(event.target.value)}>
            <option value="">{t.anyType}</option>
            {official.map((type) => (
              <option key={type.key} value={type.key}>
                {type.names[lang] ?? type.names.uz}
              </option>
            ))}
          </SelectField>
          <Button variant="secondary" onClick={() => templateInput.current?.click()} disabled={busy}>
            {t.addTemplate}
          </Button>
          <Button variant="secondary" onClick={() => exampleInput.current?.click()} disabled={busy}>
            {t.addExample}
          </Button>
          <input
            ref={templateInput}
            type="file"
            accept=".docx"
            className="sr-only"
            data-testid="org-template-input"
            onChange={(event) => {
              upload("template", event.target.files);
              event.target.value = "";
            }}
          />
          <input
            ref={exampleInput}
            type="file"
            accept=".docx,.pdf,.txt,.md"
            className="sr-only"
            data-testid="org-example-input"
            onChange={(event) => {
              upload("example", event.target.files);
              event.target.value = "";
            }}
          />
        </div>
        {section("template")}
      </section>

      <section>
        <h3 className="mb-1 text-sm font-medium">{t.examples}</h3>
        <p className="mb-2 text-xs text-ink-faint">{t.examplesHint}</p>
        {section("example")}
      </section>

      {busy ? <Spinner label={t.loading} /> : null}
      {message ? (
        <p className="text-sm text-ink-muted" role="status" data-testid="org-files-status">
          {message}
        </p>
      ) : null}
    </div>
  );
}
