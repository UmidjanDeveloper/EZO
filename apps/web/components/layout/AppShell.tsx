"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useMemo, useState, type ReactNode } from "react";
import { useApp } from "@/lib/app-state";
import { createStoredValue } from "@/lib/stored-value";
import { HistoryPanel } from "./HistoryPanel";
import { ShellContext } from "./shell-context";

const storedHistoryOpen = createStoredValue<"open" | "closed">(
  "ezo-history-panel",
  "open",
  (value): value is "open" | "closed" => value === "open" || value === "closed",
);

export function AppShell({ children }: { children: ReactNode }) {
  const { status } = useApp();
  const desktopOpen = storedHistoryOpen.useValue() === "open";
  const [mobileOpen, setMobileOpen] = useState(false);

  const shell = useMemo(
    () => ({
      historyOpen: desktopOpen,
      openHistory: () => {
        if (window.matchMedia("(min-width: 768px)").matches) storedHistoryOpen.set("open");
        else setMobileOpen(true);
      },
    }),
    [desktopOpen],
  );

  return (
    <ShellContext.Provider value={shell}>
      <div className="flex h-dvh overflow-hidden">
        <AnimatePresence initial={false}>
          {desktopOpen ? (
            <motion.aside
              key="history"
              className="hidden shrink-0 overflow-hidden border-r border-line bg-bg md:block"
              initial={{ width: 0 }}
              animate={{ width: 264 }}
              exit={{ width: 0 }}
              transition={{ type: "tween", duration: 0.2 }}
            >
              <div className="h-full w-[264px]">
                <HistoryPanel onClose={() => storedHistoryOpen.set("closed")} />
              </div>
            </motion.aside>
          ) : null}
        </AnimatePresence>

        <AnimatePresence>
          {mobileOpen ? (
            <>
              <motion.div
                className="fixed inset-0 z-40 bg-black/50 md:hidden"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                onClick={() => setMobileOpen(false)}
              />
              <motion.aside
                className="fixed inset-y-0 left-0 z-50 w-72 border-r border-line bg-bg md:hidden"
                initial={{ x: "-100%" }}
                animate={{ x: 0 }}
                exit={{ x: "-100%" }}
                transition={{ type: "tween", duration: 0.2 }}
              >
                <HistoryPanel onNavigate={() => setMobileOpen(false)} onClose={() => setMobileOpen(false)} />
              </motion.aside>
            </>
          ) : null}
        </AnimatePresence>

        <main className="flex min-w-0 flex-1 flex-col overflow-hidden">
          {status?.deployment_profile === "free-beta" ? (
            <div role="status" className="shrink-0 border-b border-line bg-panel px-3 py-2 text-xs">
              Bepul beta · AI ulanmagan. Text chat, manual memory, loyihalar, goals,
              IELTS matnli mashq va kichik Office eksportlari. PDF/EPUB/DOCX o‘qish va avtomatik vazifalar o‘chirilgan.
              Saqlangan fayllarni hozircha tahrirlab yoki o‘chirib bo‘lmaydi.
            </div>
          ) : null}
          <div className="min-h-0 flex-1">{children}</div>
        </main>
      </div>
    </ShellContext.Provider>
  );
}
