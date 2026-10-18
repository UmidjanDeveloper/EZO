"use client";

import type {
  GlossaryLanguage,
  GlossaryTermInput,
  TranslateResult,
  TranslationDomain,
  TranslationLanguage,
} from "@ezo/shared";
import { Badge, Button, Card, SelectField, TextAreaField, TextField } from "@ezo/ui";
import { Trash2 } from "lucide-react";
import { useCallback, useState } from "react";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n/context";
import { toApiError, useApiData } from "@/lib/use-api-data";
import { PageFrame } from "../pages/PageFrame";

const LANGUAGES: { code: TranslationLanguage; label: string }[] = [
  { code: "uz", label: "O'zbekcha (lotin)" },
  { code: "uz-cyrl", label: "Ўзбекча (кирилл)" },
  { code: "ru", label: "Русский" },
  { code: "en", label: "English" },
];
const GLOSSARY_LANGUAGES: GlossaryLanguage[] = ["uz", "ru", "en"];
const DOMAINS: TranslationDomain[] = ["general", "official", "academic", "business", "technical", "legal"];
const LIST_WARNINGS = ["missing_numbers", "extra_numbers", "links_changed", "names_to_check", "terms_missing", "ambiguities"] as const;
const COUNT_WARNINGS = ["empty_paragraphs", "untranslated_paragraphs", "length_warnings"] as const;
const EMPTY_TERM: GlossaryTermInput = { source_language: "uz", target_language: "en", source_term: "", target_term: "" };

/** Text translation, Uzbek Latin ↔ Cyrillic, and the glossary. Documents are translated in chat. */
export function TranslationPage() {
  const { m, f } = useI18n();
  const t = m.translation;
  const [text, setText] = useState("");
  const [source, setSource] = useState<TranslationLanguage | "auto">("auto");
  const [target, setTarget] = useState<TranslationLanguage>("en");
  const [domain, setDomain] = useState<TranslationDomain>("general");
  const [output, setOutput] = useState("");
  const [result, setResult] = useState<TranslateResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { data: terms, reload } = useApiData(useCallback(() => api.glossary(), []));
  const { data: organizations } = useApiData(useCallback(() => api.organizations(), []));
  const [term, setTerm] = useState<GlossaryTermInput>(EMPTY_TERM);

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (reason) {
      setError(toApiError(reason).message);
    } finally {
      setBusy(false);
    }
  }

  const translate = () =>
    run(async () => {
      const next = await api.translate({ text, target, source: source === "auto" ? null : source, domain });
      setResult(next);
      setOutput(next.text);
    });

  const convert = (to: "latin" | "cyrillic") =>
    run(async () => {
      const next = await api.transliterate(text, to);
      setResult(null);
      setOutput(next.text);
    });

  const addTerm = () =>
    run(async () => {
      await api.createGlossaryTerm({ ...term, source_term: term.source_term.trim(), target_term: term.target_term.trim() });
      setTerm({ ...term, source_term: "", target_term: "", note: "" });
      reload();
    });

  const removeTerm = (id: string) =>
    run(async () => {
      await api.deleteGlossaryTerm(id);
      reload();
    });

  const warnings: string[] = [];
  const quality = result?.quality;
  if (quality) {
    for (const key of LIST_WARNINGS) {
      if (quality[key].length) warnings.push(f(t.warn[key], { list: quality[key].join(", ") }));
    }
    for (const key of COUNT_WARNINGS) {
      if (quality[key].length) warnings.push(f(t.warn[key], { count: quality[key].length }));
    }
    if (quality.script_note) warnings.push(t.warn.script_note);
  }
  const orgName = (id?: string | null) => organizations?.find((org) => org.id === id)?.name;

  return (
    <PageFrame title={t.title} subtitle={t.subtitle}>
      <div className="flex flex-col gap-4">
        <Card className="p-4" data-testid="translate-card">
          <div className="grid gap-3 sm:grid-cols-3">
            <SelectField label={t.source} value={source} onChange={(e) => setSource(e.target.value as TranslationLanguage | "auto")}>
              <option value="auto">{t.auto}</option>
              {LANGUAGES.map((lang) => (
                <option key={lang.code} value={lang.code}>
                  {lang.label}
                </option>
              ))}
            </SelectField>
            <SelectField label={t.target} value={target} onChange={(e) => setTarget(e.target.value as TranslationLanguage)} data-testid="translate-target">
              {LANGUAGES.map((lang) => (
                <option key={lang.code} value={lang.code}>
                  {lang.label}
                </option>
              ))}
            </SelectField>
            <SelectField label={t.domain} value={domain} onChange={(e) => setDomain(e.target.value as TranslationDomain)}>
              {DOMAINS.map((name) => (
                <option key={name} value={name}>
                  {t.domains[name]}
                </option>
              ))}
            </SelectField>
          </div>
          <div className="mt-3 grid gap-3 md:grid-cols-2">
            <TextAreaField label={t.input} rows={8} value={text} onChange={(e) => setText(e.target.value)} data-testid="translate-input" />
            <TextAreaField label={t.output} rows={8} value={output} readOnly data-testid="translate-output" />
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <Button variant="primary" onClick={() => void translate()} disabled={busy || !text.trim()} data-testid="translate-run">
              {t.translate}
            </Button>
            <Button onClick={() => void convert("cyrillic")} disabled={busy || !text.trim()} data-testid="translit-cyrillic">
              {t.toCyrillic}
            </Button>
            <Button onClick={() => void convert("latin")} disabled={busy || !text.trim()} data-testid="translit-latin">
              {t.toLatin}
            </Button>
            {result ? <Badge>{result.method === "model" ? t.method.model : t.method.transliteration}</Badge> : null}
          </div>
          <p className="mt-2 text-xs text-ink-faint">{t.scriptNote}</p>
          {error ? (
            <p className="mt-3 text-sm text-danger" role="alert" data-testid="translate-error">
              {error}
            </p>
          ) : null}
          {result ? (
            <div className="mt-3 rounded-xl border border-line p-3 text-sm" data-testid="translate-checks">
              <p className="mb-1 font-medium">{t.checks}</p>
              {warnings.length ? (
                <ul className="list-disc pl-5 text-ink-muted">
                  {warnings.map((line) => (
                    <li key={line}>{line}</li>
                  ))}
                </ul>
              ) : (
                <p className="text-ink-muted">{t.checksOk}</p>
              )}
            </div>
          ) : null}
        </Card>

        <Card className="p-4" data-testid="glossary">
          <h2 className="mb-1 font-medium">{t.glossary}</h2>
          <p className="mb-3 text-sm text-ink-muted">{t.glossaryIntro}</p>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <SelectField
              label={t.source}
              value={term.source_language}
              onChange={(e) => setTerm({ ...term, source_language: e.target.value as GlossaryLanguage })}
            >
              {GLOSSARY_LANGUAGES.map((code) => (
                <option key={code} value={code}>
                  {code}
                </option>
              ))}
            </SelectField>
            <SelectField
              label={t.target}
              value={term.target_language}
              onChange={(e) => setTerm({ ...term, target_language: e.target.value as GlossaryLanguage })}
            >
              {GLOSSARY_LANGUAGES.map((code) => (
                <option key={code} value={code}>
                  {code}
                </option>
              ))}
            </SelectField>
            <SelectField
              label={t.organization}
              value={term.organization_id ?? ""}
              onChange={(e) => setTerm({ ...term, organization_id: e.target.value || null })}
            >
              <option value="">{t.allOrganizations}</option>
              {(organizations ?? []).map((org) => (
                <option key={org.id} value={org.id}>
                  {org.name}
                </option>
              ))}
            </SelectField>
            <TextField
              label={t.sourceTerm}
              value={term.source_term}
              onChange={(e) => setTerm({ ...term, source_term: e.target.value })}
              data-testid="glossary-source"
            />
            <TextField
              label={t.targetTerm}
              value={term.target_term}
              onChange={(e) => setTerm({ ...term, target_term: e.target.value })}
              data-testid="glossary-target"
            />
            <TextField label={t.note} value={term.note ?? ""} onChange={(e) => setTerm({ ...term, note: e.target.value })} />
          </div>
          <Button
            className="mt-3"
            onClick={() => void addTerm()}
            disabled={busy || !term.source_term.trim() || !term.target_term.trim() || term.source_language === term.target_language}
            data-testid="glossary-add"
          >
            {t.add}
          </Button>
          {terms && terms.length ? (
            <ul className="mt-4 divide-y divide-line text-sm" data-testid="glossary-list">
              {terms.map((entry) => (
                <li key={entry.id} className="flex items-center justify-between gap-2 py-2">
                  <span>
                    <Badge className="mr-2">
                      {entry.source_language} → {entry.target_language}
                    </Badge>
                    {entry.source_term} → <strong>{entry.target_term}</strong>
                    {entry.note ? <span className="text-ink-faint"> · {entry.note}</span> : null}
                    {entry.organization_id ? <span className="text-ink-faint"> · {orgName(entry.organization_id)}</span> : null}
                  </span>
                  <Button variant="ghost" size="icon" aria-label={t.remove} onClick={() => void removeTerm(entry.id)}>
                    <Trash2 size={16} />
                  </Button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-4 text-sm text-ink-faint">{t.emptyGlossary}</p>
          )}
        </Card>
        <p className="text-xs text-ink-faint">{t.interpretNote}</p>
      </div>
    </PageFrame>
  );
}
