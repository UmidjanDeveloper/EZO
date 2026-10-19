"use client";

import type { HumorPreference, LanguageCode, ResponseLanguage, User } from "@ezo/shared";
import { Badge, Card, SelectField, Spinner, TextField } from "@ezo/ui";
import { useCallback, useState } from "react";
import { api, storedToken } from "@/lib/api";
import { useApp } from "@/lib/app-state";
import { UI_LANGUAGES, useI18n } from "@/lib/i18n/context";
import { useTheme, type ThemeChoice } from "@/lib/theme";
import { useApiData } from "@/lib/use-api-data";
import { CareerCard } from "../settings/CareerCard";
import { OrganizationCard } from "../settings/OrganizationCard";
import { PageFrame } from "./PageFrame";

export function SettingsPage() {
  const { m, f, language, setLanguage } = useI18n();
  const { choice, setChoice } = useTheme();
  const { status, statusError, refreshStatus, showDebug, setShowDebug } = useApp();
  const { data: loadedUser, error: loadError } = useApiData(useCallback(() => api.me(), []));
  const { data: voiceStatus } = useApiData(useCallback(() => api.voiceStatus(), []));
  const [updatedUser, setUser] = useState<User | null>(null);
  const user = updatedUser ?? loadedUser;
  const [actionError, setError] = useState<string | null>(null);
  const error = actionError ?? loadError?.message ?? null;
  const token = storedToken.useValue();
  const [saved, setSaved] = useState(false);

  async function update(changes: Partial<User["preferences"]>) {
    try {
      const next = await api.updatePreferences(changes);
      setUser(next);
      setSaved(true);
      window.setTimeout(() => setSaved(false), 1500);
    } catch (reason) {
      setError((reason as Error).message);
    }
  }

  function changeUiLanguage(code: LanguageCode) {
    setLanguage(code);
    void update({ ui_language: code });
  }

  function saveToken(value: string) {
    storedToken.set(value ? value : null);
  }

  const prefs = user?.preferences;

  return (
    <PageFrame title={m.settings.title} actions={saved ? <Badge tone="success">{m.common.saved}</Badge> : null}>
      {error ? <p className="mb-4 text-sm text-danger">{error}</p> : null}
      <div className="flex flex-col gap-6">
        <Card>
          <h2 className="mb-4 font-medium">{m.settings.preferences}</h2>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <SelectField
              label={m.settings.interfaceLanguage}
              value={language}
              onChange={(e) => changeUiLanguage(e.target.value as LanguageCode)}
              data-testid="ui-language"
            >
              {UI_LANGUAGES.map((item) => (
                <option key={item.code} value={item.code}>
                  {item.label}
                </option>
              ))}
            </SelectField>
            <SelectField
              label={m.settings.theme}
              value={choice}
              onChange={(e) => setChoice(e.target.value as ThemeChoice)}
            >
              <option value="system">{m.settings.themeSystem}</option>
              <option value="light">{m.settings.themeLight}</option>
              <option value="dark">{m.settings.themeDark}</option>
            </SelectField>
            {prefs ? (
              <>
                <SelectField
                  label={m.settings.responseLanguage}
                  value={prefs.response_language}
                  onChange={(e) => void update({ response_language: e.target.value as ResponseLanguage })}
                >
                  <option value="auto">{m.settings.auto}</option>
                  {UI_LANGUAGES.map((item) => (
                    <option key={item.code} value={item.code}>
                      {item.label}
                    </option>
                  ))}
                </SelectField>
                <SelectField
                  label={m.settings.humor}
                  value={prefs.humor}
                  onChange={(e) => void update({ humor: e.target.value as HumorPreference })}
                >
                  <option value="default">{m.settings.humorDefault}</option>
                  <option value="off">{m.settings.humorOff}</option>
                  <option value="light">{m.settings.humorLight}</option>
                  <option value="normal">{m.settings.humorNormal}</option>
                </SelectField>
              </>
            ) : (
              <Spinner label={m.common.loading} />
            )}
          </div>
          {prefs ? (
            <label className="mt-4 flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                className="h-4 w-4 accent-[var(--accent)]"
                checked={prefs.auto_memory}
                onChange={(e) => void update({ auto_memory: e.target.checked })}
              />
              {m.settings.autoMemory}
            </label>
          ) : null}
          {status?.debug_traces ? (
            <label className="mt-2 flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                className="h-4 w-4 accent-[var(--accent)]"
                checked={showDebug}
                onChange={(e) => setShowDebug(e.target.checked)}
              />
              {m.settings.debug}
            </label>
          ) : null}
          <div className="mt-4 max-w-md">
            <TextField
              label={m.settings.apiToken}
              type="password"
              autoComplete="off"
              value={token}
              onChange={(e) => saveToken(e.target.value)}
              onBlur={() => void refreshStatus()}
              hint={m.settings.apiTokenHint}
            />
          </div>
        </Card>

        <OrganizationCard />
        <CareerCard />

        <Card data-testid="system-status">
          <h2 className="mb-4 font-medium">{m.settings.system}</h2>
          {statusError ? (
            <div className="text-sm">
              <p className="text-danger">{statusError.message}</p>
              {statusError.hint ? <p className="mt-1 text-ink-muted">{statusError.hint}</p> : null}
            </div>
          ) : !status ? (
            <Spinner label={m.common.loading} />
          ) : (
            <div className="flex flex-col gap-5 text-sm">
              <div className="flex flex-wrap gap-2">
                <Badge>
                  {m.settings.version} {status.version}
                </Badge>
                <Badge>
                  {m.settings.database}: {status.database}
                </Badge>
                {status.offline_mode ? <Badge tone="warning">{m.settings.offline}</Badge> : null}
              </div>

              <section>
                <h3 className="mb-2 font-medium">{m.settings.providers}</h3>
                <ul className="flex flex-col gap-1.5">
                  {status.providers.map((provider) => (
                    <li key={provider.name} className="flex flex-wrap items-center gap-2">
                      <span className="w-36">{provider.display_name}</span>
                      <Badge tone={provider.configured ? "success" : "neutral"}>
                        {provider.configured ? m.settings.configured : m.settings.notConfigured}
                      </Badge>
                      {provider.capabilities.length ? (
                        <span className="text-xs text-ink-faint">{provider.capabilities.join(", ")}</span>
                      ) : null}
                    </li>
                  ))}
                </ul>
              </section>

              <section>
                <h3 className="mb-2 font-medium">{m.settings.routes}</h3>
                <ul className="flex flex-col gap-1.5">
                  {Object.entries(status.routing.routes).map(([name, route]) => (
                    <li key={name} className="flex flex-wrap items-baseline gap-2">
                      <span className="w-28 font-mono text-xs">{name}</span>
                      <span className="font-mono text-xs text-ink-muted">
                        {route.active_candidates.map((c) => `${c.provider}/${c.model}`).join(" → ") || "–"}
                      </span>
                    </li>
                  ))}
                </ul>
              </section>

              <section data-testid="voice-settings">
                <h3 className="mb-2 font-medium">{m.settings.voice}</h3>
                <p className="text-ink-muted">
                  {voiceStatus && voiceStatus.speech_to_text.length + voiceStatus.text_to_speech.length > 0
                    ? f(m.settings.voiceServer, {
                        providers: [...new Set([...voiceStatus.speech_to_text, ...voiceStatus.text_to_speech])].join(" → "),
                      })
                    : m.settings.voiceBrowser}
                </p>
                <p className="mt-1 text-xs text-ink-faint">{m.settings.voiceNoAudio}</p>
              </section>

              <section>
                <h3 className="mb-2 font-medium">{m.settings.personality}</h3>
                <p className="text-ink-muted">{status.personality.traits.join(" · ")}</p>
              </section>
            </div>
          )}
        </Card>
      </div>
    </PageFrame>
  );
}
