"use client";

import type { ReactNode } from "react";
import { AppProvider } from "@/lib/app-state";
import { I18nProvider } from "@/lib/i18n/context";
import { ThemeProvider } from "@/lib/theme";

export function Providers({ children }: { children: ReactNode }) {
  return (
    <ThemeProvider>
      <I18nProvider>
        <AppProvider>{children}</AppProvider>
      </I18nProvider>
    </ThemeProvider>
  );
}
