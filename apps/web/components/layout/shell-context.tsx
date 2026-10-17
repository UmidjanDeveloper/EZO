"use client";

import { PanelLeftOpen } from "lucide-react";
import { createContext, useContext } from "react";
import { cn } from "@ezo/ui";
import { useI18n } from "@/lib/i18n/context";

interface ShellValue {
  /** Whether the history panel is visible on desktop. */
  historyOpen: boolean;
  openHistory: () => void;
}

export const ShellContext = createContext<ShellValue>({ historyOpen: true, openHistory: () => undefined });

export function useShell(): ShellValue {
  return useContext(ShellContext);
}

/** Opens the conversation history: always shown on phones, on desktop only when the panel is hidden. */
export function HistoryButton({ className }: { className?: string }) {
  const { m } = useI18n();
  const { historyOpen, openHistory } = useShell();
  return (
    <button
      type="button"
      onClick={openHistory}
      aria-label={m.nav.openHistory}
      title={m.nav.openHistory}
      data-testid="open-history"
      className={cn(
        "rounded-lg p-1.5 text-ink-muted transition-colors hover:bg-surface-2 hover:text-ink",
        historyOpen && "md:hidden",
        className,
      )}
    >
      <PanelLeftOpen size={19} />
    </button>
  );
}
