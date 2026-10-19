"use client";

import type { OrganizationFormatting, OrganizationProfile, OrganizationProfileInput } from "@ezo/shared";
import { Button, Card, SelectField, TextAreaField, TextField } from "@ezo/ui";
import { useCallback, useState } from "react";
import { api } from "@/lib/api";
import { saveBlob } from "@/lib/download";
import { useI18n } from "@/lib/i18n/context";
import { useApiData } from "@/lib/use-api-data";
import { OrganizationFiles } from "./OrganizationFiles";

const TYPES = ["government", "university", "school", "company", "research", "nonprofit", "other"] as const;
const EMPTY: OrganizationProfileInput = { name: "", org_type: "government", is_default: true };
const DEFAULT_FORMATTING: OrganizationFormatting = {
  font_name: "Times New Roman",
  font_size: 14,
  line_spacing: 1.15,
  indent_cm: 1.25,
  margins_cm: { top: 2, bottom: 2, left: 3, right: 1.5 },
};
const MARGINS = ["top", "bottom", "left", "right"] as const;

/** "mutasaddi = mas'ul" per line ⇄ {"mutasaddi": "mas'ul"}. */
export function parseTerms(text: string): Record<string, string> {
  const terms: Record<string, string> = {};
  for (const line of text.split("\n")) {
    const [avoid, ...rest] = line.split("=");
    const use = rest.join("=").trim();
    if (avoid?.trim() && use) terms[avoid.trim()] = use;
  }
  return terms;
}

export function formatTerms(terms: Record<string, string> | undefined): string {
  return Object.entries(terms ?? {})
    .map(([avoid, use]) => `${avoid} = ${use}`)
    .join("\n");
}

/** The organization EZO writes for: letterhead, contacts and house style. */
export function OrganizationCard() {
  const { m } = useI18n();
  const { data, error } = useApiData(useCallback(() => api.organizations(), []));
  // `undefined`: nothing saved or deleted yet in this session, so show what was loaded.
  const [saved, setSaved] = useState<OrganizationProfile | null | undefined>(undefined);
  const profile = saved === undefined ? (data?.[0] ?? null) : saved;
  const [edits, setEdits] = useState<OrganizationProfileInput | null>(null);
  const form = edits ?? (profile ? { ...profile } : EMPTY);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [terms, setTerms] = useState<string | null>(null);
  const termsText = terms ?? formatTerms(form.terminology);
  const formatting = form.formatting ?? DEFAULT_FORMATTING;

  function setFormatting(update: Partial<OrganizationFormatting>) {
    setForm((current) => ({ ...current, formatting: { ...formatting, ...update } }));
  }

  function number(value: string, fallback: number): number {
    const parsed = Number(value.replace(",", "."));
    return Number.isFinite(parsed) ? parsed : fallback;
  }

  function setForm(update: (current: OrganizationProfileInput) => OrganizationProfileInput) {
    setEdits(update(form));
  }

  function field(key: keyof OrganizationProfileInput) {
    return {
      value: (form[key] as string | null | undefined) ?? "",
      onChange: (event: { target: { value: string } }) =>
        setForm((current) => ({ ...current, [key]: event.target.value })),
    };
  }

  async function save() {
    setBusy(true);
    setMessage(null);
    try {
      const body = { ...form, terminology: parseTerms(termsText), formatting, is_default: true };
      const next = profile ? await api.updateOrganization(profile.id, body) : await api.createOrganization(body);
      setSaved(next);
      setEdits(null);
      setTerms(null);
      setMessage(m.common.saved);
    } catch (reason) {
      setMessage((reason as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!profile || !window.confirm(m.organization.confirmDelete)) return;
    setBusy(true);
    try {
      await api.deleteOrganization(profile.id);
      setSaved(null);
      setEdits(null);
      setTerms(null);
    } catch (reason) {
      setMessage((reason as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card data-testid="organization-profile">
      <h2 className="mb-1 font-medium">{m.organization.title}</h2>
      <p className="mb-4 text-sm text-ink-muted">{m.organization.intro}</p>
      {error ? <p className="mb-3 text-sm text-danger">{error.message}</p> : null}
      {!profile ? <p className="mb-3 text-sm text-ink-faint">{m.organization.empty}</p> : null}
      <div className="grid gap-3 sm:grid-cols-2">
        <TextField label={m.organization.name} {...field("name")} data-testid="org-name" required />
        <SelectField
          label={m.organization.type}
          value={form.org_type}
          onChange={(event) =>
            setForm((current) => ({
              ...current,
              org_type: event.target.value as OrganizationProfileInput["org_type"],
            }))
          }
        >
          {TYPES.map((type) => (
            <option key={type} value={type}>
              {m.organization.types[type]}
            </option>
          ))}
        </SelectField>
        <TextField label={m.organization.department} {...field("department")} />
        <TextField label={m.organization.address} {...field("address")} />
        <TextField label={m.organization.phone} {...field("phone")} />
        <TextField label={m.organization.email} {...field("email")} />
        <TextField label={m.organization.website} {...field("website")} />
        <TextField label={m.organization.headPosition} {...field("head_position")} />
        <TextField label={m.organization.headName} {...field("head_name")} />
      </div>
      <div className="mt-3 grid gap-3">
        <TextAreaField label={m.organization.letterhead} rows={3} {...field("letterhead")} />
        <TextAreaField label={m.organization.styleNotes} rows={3} {...field("style_notes")} />
        <TextAreaField
          label={m.organization.terminology}
          hint={m.organization.terminologyHint}
          rows={3}
          value={termsText}
          onChange={(event) => setTerms(event.target.value)}
          data-testid="org-terms"
        />
      </div>
      <fieldset className="mt-4 rounded-lg border border-line p-3">
        <legend className="px-1 text-sm font-medium">{m.organization.formatting}</legend>
        <div className="grid gap-3 sm:grid-cols-4">
          <TextField
            label={m.organization.font}
            value={formatting.font_name}
            onChange={(event) => setFormatting({ font_name: event.target.value })}
            data-testid="org-font"
          />
          <TextField
            label={m.organization.fontSize}
            type="number"
            min={8}
            max={20}
            step={0.5}
            value={formatting.font_size}
            onChange={(event) => setFormatting({ font_size: number(event.target.value, formatting.font_size) })}
            data-testid="org-font-size"
          />
          <TextField
            label={m.organization.lineSpacing}
            type="number"
            min={1}
            max={3}
            step={0.05}
            value={formatting.line_spacing}
            onChange={(event) => setFormatting({ line_spacing: number(event.target.value, formatting.line_spacing) })}
          />
          <TextField
            label={m.organization.indent}
            type="number"
            min={0}
            max={3}
            step={0.25}
            value={formatting.indent_cm}
            onChange={(event) => setFormatting({ indent_cm: number(event.target.value, formatting.indent_cm) })}
          />
          {MARGINS.map((side) => (
            <TextField
              key={side}
              label={m.organization.margins[side]}
              type="number"
              min={0.5}
              max={5}
              step={0.25}
              value={formatting.margins_cm[side]}
              onChange={(event) =>
                setFormatting({
                  margins_cm: { ...formatting.margins_cm, [side]: number(event.target.value, formatting.margins_cm[side]) },
                })
              }
            />
          ))}
        </div>
      </fieldset>
      <div className="mt-4 flex items-center gap-2">
        <Button onClick={() => void save()} disabled={busy || !form.name.trim()} data-testid="org-save">
          {m.organization.save}
        </Button>
        {profile ? (
          <>
            <Button
              variant="secondary"
              disabled={busy}
              data-testid="org-export"
              onClick={() =>
                void api
                  .exportOrganization(profile.id)
                  .then(({ blob, filename }) => saveBlob(blob, filename))
                  .catch((reason: Error) => setMessage(reason.message))
              }
            >
              {m.organization.export}
            </Button>
            <Button variant="ghost" onClick={() => void remove()} disabled={busy} data-testid="org-delete">
              {m.organization.remove}
            </Button>
          </>
        ) : null}
        {message ? (
          <span className="text-sm text-ink-muted" role="status" data-testid="org-status">
            {message}
          </span>
        ) : null}
      </div>
      {profile ? (
        <OrganizationFiles key={profile.id} profile={profile} onProfile={(next) => setSaved(next)} />
      ) : (
        <p className="mt-4 text-xs text-ink-faint">{m.organization.filesAfterSave}</p>
      )}
    </Card>
  );
}
