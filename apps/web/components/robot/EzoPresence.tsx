"use client";

import { cn } from "@ezo/ui";
import { motion, useReducedMotion } from "framer-motion";
import { presenceLook, TONE_VAR, type EzoState } from "@/lib/ezo-state";
import { EzoHumanoid } from "./EzoHumanoid";

interface EzoPresenceProps {
  state: EzoState;
  size?: number;
  /** Text under the presence, e.g. "Searching…". Announced politely to screen readers. */
  label?: string;
  className?: string;
}

/** Shared energy presence for secondary views; the canvas owns all state animation. */
export function EzoPresence({ state, size = 260, label, className }: EzoPresenceProps) {
  const look = presenceLook(state);
  return <div className={cn("relative flex flex-col items-center", className)} data-testid="ezo-presence" data-state={state} aria-busy={look.busy}>
    <div className="relative" style={{ width: size, height: size }}><EzoHumanoid state={state} label={label} className="absolute inset-0" style="energy" /></div>
    {label ? <p className="mt-3 text-sm font-medium tracking-wide text-ink-muted" aria-live="polite" data-testid="ezo-presence-label">{label}</p> : null}
  </div>;
}

/** A small "what EZO is doing" indicator for headers. Hidden while idle. */
export function EzoStatus({ state, label }: { state: EzoState; label: string }) {
  const reduce = useReducedMotion() ?? false;
  if (state === "idle") return null;
  const look = presenceLook(state);
  const tone = TONE_VAR[look.tone];
  return (
    <span
      className="flex items-center gap-1.5 rounded-full border border-line bg-surface px-2.5 py-1 text-xs text-ink-muted"
      role="status"
      data-testid="ezo-status"
      data-state={state}
    >
      <span className="relative flex h-2.5 w-2.5">
        {look.busy && !reduce ? (
          <motion.span
            className="absolute inset-0 rounded-full"
            style={{ background: tone }}
            animate={{ scale: [1, 2.2], opacity: [0.6, 0] }}
            transition={{ duration: 1.4, repeat: Infinity, ease: "easeOut" }}
          />
        ) : null}
        <span className="relative h-2.5 w-2.5 rounded-full" style={{ background: tone }} />
      </span>
      {label}
    </span>
  );
}
