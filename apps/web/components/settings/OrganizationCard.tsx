"use client";

import type { OrganizationProfile, OrganizationProfileInput } from "@ezo/shared";
import { Button, Card, SelectField, TextAreaField, TextField } from "@ezo/ui";
import { useCallback, useState } from "react";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n/context";
import { useApiData } from "@/lib/use-api-data";

const TYPES = ["government", "university", "school", "company", "research", "nonprofit", "other"] as const;
const EMPTY: OrganizationProfileInput = { name: "", org_type: "government", is_default: true };

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
      const body = { ...form, is_default: true };
      const next = profile ? await api.updateOrganization(profile.id, body) : await api.createOrganization(body);
      setSaved(next);
      setEdits(null);
      setMessage(m.common.saved);
    } catch (reason) {
      setMessage((reason as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!profile) return;
    setBusy(true);
    try {
      await api.deleteOrganization(profile.id);
      setSaved(null);
      setEdits(null);
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
      </div>
      <div className="mt-4 flex items-center gap-2">
        <Button onClick={() => void save()} disabled={busy || !form.name.trim()} data-testid="org-save">
          {m.organization.save}
        </Button>
        {profile ? (
          <Button variant="ghost" onClick={() => void remove()} disabled={busy}>
            {m.organization.remove}
          </Button>
        ) : null}
        {message ? (
          <span className="text-sm text-ink-muted" role="status">
            {message}
          </span>
        ) : null}
      </div>
    </Card>
  );
}
