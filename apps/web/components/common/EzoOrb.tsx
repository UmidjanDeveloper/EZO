"use client";

import { motion, useReducedMotion } from "framer-motion";
import { cn } from "@ezo/ui";

/** EZO's visual signature: a calm, slowly breathing turquoise-lapis orb. */
export function EzoOrb({ size = 96, active = false, className }: { size?: number; active?: boolean; className?: string }) {
  const reduce = useReducedMotion();
  return (
    <div className={cn("relative", className)} style={{ width: size, height: size }} aria-hidden>
      <motion.div
        className="absolute inset-0 rounded-full"
        style={{
          background: "radial-gradient(circle at 40% 40%, var(--accent), var(--accent-2) 70%)",
          filter: `blur(${Math.max(4, Math.round(size / 3))}px)`,
        }}
        animate={reduce ? undefined : { opacity: active ? [0.55, 0.9, 0.55] : [0.35, 0.55, 0.35], scale: [0.95, 1.05, 0.95] }}
        transition={{ duration: active ? 1.6 : 5, repeat: Infinity, ease: "easeInOut" }}
      />
      <motion.div
        className="absolute inset-[14%] rounded-full"
        style={{
          background:
            "radial-gradient(circle at 32% 28%, rgb(255 255 255 / 0.85), transparent 28%), radial-gradient(circle at 50% 55%, var(--accent), var(--accent-2) 75%)",
          boxShadow: "inset 0 -8px 24px rgb(0 0 0 / 0.25)",
        }}
        animate={reduce ? undefined : { rotate: 360 }}
        transition={{ duration: active ? 6 : 24, repeat: Infinity, ease: "linear" }}
      />
    </div>
  );
}
