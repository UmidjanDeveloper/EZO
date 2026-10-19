"use client";

import type { CareerProfile } from "@ezo/shared";
import { Button, Card, TextAreaField, TextField } from "@ezo/ui";
import { useCallback, useState } from "react";
import { api } from "@/lib/api";
import { careerLines, type CareerLines, parseCareerLines } from "@/lib/career-lines";
import { useI18n } from "@/lib/i18n/context";
import { useApiData } from "@/lib/use-api-data";

type Basics = Pick<CareerProfile, "full_name" | "headline" | "email" | "phone" | "location" | "summary">;
const EMPTY_BASICS: Basics = { full_name: "" };

/** The career profile a CV and application letters are built from (facts only). */
export function CareerCard() {
  const { m } = useI18n();
  const t = m.career;
  const { data, error } = useApiData(useCallback(() => api.careerProfile(), []));
  // `undefined`: nothing saved or deleted in this session yet, so show what was loaded.
  const [saved, setSaved] = useState<CareerProfile | null | undefined>(undefined);
  const profile = saved === undefined ? data : saved;
  const [basicsEdit, setBasics] = useState<Basics | null>(null);
  const [linesEdit, setLines] = useState<CareerLines | null>(null);
  const basics = basicsEdit ?? (profile ? { ...profile } : EMPTY_BASICS);
  const lines = linesEdit ?? careerLines(profile ?? null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  function basic(key: keyof Basics) {
    return {
      value: (basics[key] as string | null | undefined) ?? "",
      onChange: (event: { target: { value: string } }) => setBasics({ ...basics, [key]: event.target.value }),
    };
  }

  function line(key: keyof CareerLines) {
    return {
      value: lines[key],
      onChange: (event: { target: { value: string } }) => setLines({ ...lines, [key]: event.target.value }),
    };
  }

  async function save() {
    setBusy(true);
    setMessage(null);
    try {
      const body: CareerProfile = {
        ...profile,
        ...basics,
        full_name: basics.full_name.trim(),
        ...parseCareerLines(lines),
      };
      setSaved(await api.saveCareerProfile(body));
      setBasics(null);
      setLines(null);
      setMessage(m.common.saved);
    } catch (reason) {
      setMessage((reason as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    setBusy(true);
    try {
      await api.deleteCareerProfile();
      setSaved(null);
      setBasics(null);
      setLines(null);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card data-testid="career-profile">
      <h2 className="mb-1 font-medium">{t.title}</h2>
      <p className="mb-4 text-sm text-ink-muted">{t.intro}</p>
      {error ? <p className="mb-3 text-sm text-danger">{error.message}</p> : null}
      {!profile ? <p className="mb-3 text-sm text-ink-faint">{t.empty}</p> : null}
      <div className="grid gap-3 sm:grid-cols-2">
        <TextField label={t.fullName} {...basic("full_name")} data-testid="career-name" required />
        <TextField label={t.headline} {...basic("headline")} />
        <TextField label={t.email} {...basic("email")} />
        <TextField label={t.phone} {...basic("phone")} />
        <TextField label={t.location} {...basic("location")} />
      </div>
      <div className="mt-3 grid gap-3">
        <TextAreaField label={t.summary} rows={2} {...basic("summary")} />
        <TextAreaField label={t.experience} hint={t.experienceHint} rows={3} {...line("experience")} data-testid="career-experience" />
        <TextAreaField label={t.education} hint={t.educationHint} rows={2} {...line("education")} />
        <TextField label={t.skills} {...line("skills")} data-testid="career-skills" />
        <TextAreaField label={t.languages} hint={t.languagesHint} rows={2} {...line("languages")} />
        <TextAreaField label={t.certificates} hint={t.certificatesHint} rows={2} {...line("certificates")} />
      </div>
      <div className="mt-4 flex items-center gap-2">
        <Button onClick={() => void save()} disabled={busy || !basics.full_name.trim()} data-testid="career-save">
          {t.save}
        </Button>
        {profile ? (
          <Button variant="ghost" onClick={() => void remove()} disabled={busy}>
            {t.remove}
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
