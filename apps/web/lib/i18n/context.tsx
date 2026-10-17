"use client";

import type { LanguageCode } from "@ezo/shared";
import { createContext, useContext, useEffect, useMemo, type ReactNode } from "react";
import { createStoredValue } from "../stored-value";
import { dictionaries, format, type Messages } from "./messages";

const STORAGE_KEY = "ezo-ui-language";
export const UI_LANGUAGES: { code: LanguageCode; label: string }[] = [
  { code: "uz", label: "O‘zbekcha" },
  { code: "en", label: "English" },
  { code: "ru", label: "Русский" },
];

interface I18nValue {
  language: LanguageCode;
  m: Messages;
  setLanguage: (language: LanguageCode) => void;
  f: typeof format;
}

const I18nContext = createContext<I18nValue | null>(null);

export const storedUiLanguage = createStoredValue<LanguageCode>(
  STORAGE_KEY,
  "uz",
  (value): value is LanguageCode => value === "uz" || value === "en" || value === "ru",
);

export function I18nProvider({ children }: { children: ReactNode }) {
  const language = storedUiLanguage.useValue();

  useEffect(() => {
    document.documentElement.lang = language;
  }, [language]);

  const value = useMemo(
    () => ({ language, m: dictionaries[language], setLanguage: storedUiLanguage.set, f: format }),
    [language],
  );
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nValue {
  const value = useContext(I18nContext);
  if (!value) throw new Error("useI18n must be used inside I18nProvider");
  return value;
}
