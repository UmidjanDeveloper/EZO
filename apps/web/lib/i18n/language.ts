import type { LanguageCode } from "@ezo/shared";
import { createStoredValue } from "../stored-value";

/** The interface language chosen in this browser (uz by default). */
export const storedUiLanguage = createStoredValue<LanguageCode>(
  "ezo-ui-language",
  "uz",
  (value): value is LanguageCode => value === "uz" || value === "en" || value === "ru",
);
