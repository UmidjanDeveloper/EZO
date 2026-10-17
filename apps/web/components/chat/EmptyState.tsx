"use client";

import { motion } from "framer-motion";
import { useI18n } from "@/lib/i18n/context";
import { EzoPresence } from "../robot/EzoPresence";

export function EmptyState({ onPick }: { onPick: (text: string) => void }) {
  const { m } = useI18n();
  return (
    <div className="flex flex-1 flex-col items-center justify-center px-4 py-8 text-center">
      <motion.div initial={{ opacity: 0, scale: 0.92 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.6 }}>
        <EzoPresence state="idle" size={230} className="max-h-[36vh] max-w-[62vw]" />
      </motion.div>
      <motion.h1
        className="mt-4 text-2xl font-semibold sm:text-3xl"
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.15, duration: 0.5 }}
      >
        {m.chat.greeting}
      </motion.h1>
      <motion.p
        className="mt-2 max-w-md text-sm text-ink-muted"
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.25, duration: 0.5 }}
      >
        {m.chat.emptySubtitle}
      </motion.p>
      <div className="mt-6 flex max-w-2xl flex-wrap justify-center gap-2">
        {m.chat.suggestions.map((suggestion, index) => (
          <motion.button
            key={suggestion}
            type="button"
            onClick={() => onPick(suggestion)}
            className="rounded-full border border-line bg-surface px-4 py-2 text-sm text-ink-muted transition-colors hover:border-accent/50 hover:text-ink"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.35 + index * 0.05 }}
          >
            {suggestion}
          </motion.button>
        ))}
      </div>
    </div>
  );
}
