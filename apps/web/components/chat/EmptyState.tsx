"use client";

import { motion } from "framer-motion";
import { useI18n } from "@/lib/i18n/context";
import { EzoOrb } from "../common/EzoOrb";

export function EmptyState({ onPick }: { onPick: (text: string) => void }) {
  const { m } = useI18n();
  return (
    <div className="flex flex-1 flex-col items-center justify-center px-4 py-10 text-center">
      <motion.div initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.6 }}>
        <EzoOrb size={112} />
      </motion.div>
      <motion.h1
        className="mt-6 text-4xl font-semibold tracking-[0.3em] sm:text-5xl"
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1, duration: 0.5 }}
      >
        EZO
      </motion.h1>
      <motion.p
        className="mt-3 text-lg text-ink"
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.2, duration: 0.5 }}
      >
        {m.product.tagline}
      </motion.p>
      <p className="mt-2 max-w-md text-sm text-ink-muted">{m.chat.emptySubtitle}</p>
      <div className="mt-8 grid w-full max-w-2xl grid-cols-1 gap-2 sm:grid-cols-2">
        {m.chat.suggestions.map((suggestion, index) => (
          <motion.button
            key={suggestion}
            type="button"
            onClick={() => onPick(suggestion)}
            className="rounded-xl border border-line bg-surface px-4 py-3 text-left text-sm text-ink-muted transition-colors hover:border-accent/50 hover:text-ink"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3 + index * 0.05 }}
          >
            {suggestion}
          </motion.button>
        ))}
      </div>
    </div>
  );
}
