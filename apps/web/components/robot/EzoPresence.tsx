"use client";

import { cn } from "@ezo/ui";
import { motion, useReducedMotion, type Transition } from "framer-motion";
import { presenceLook, TONE_VAR, type EzoState } from "@/lib/ezo-state";
import { EzoRobot } from "./EzoRobot";

interface EzoPresenceProps {
  state: EzoState;
  size?: number;
  /** Text under the orb, e.g. "Searching…". Announced politely to screen readers. */
  label?: string;
  className?: string;
}

const C = 100; // SVG centre (viewBox 0 0 200 200)
const spinForever = (duration: number): Transition => ({ duration, repeat: Infinity, ease: "linear" });
const pulse = (duration: number, delay = 0): Transition => ({ duration, delay, repeat: Infinity, ease: "easeInOut" });

/** Arc path on the orb ring, from `start` to `end` degrees (0° = top). */
function arc(radius: number, start: number, end: number): string {
  const point = (deg: number) => {
    const rad = ((deg - 90) * Math.PI) / 180;
    return `${(C + radius * Math.cos(rad)).toFixed(2)} ${(C + radius * Math.sin(rad)).toFixed(2)}`;
  };
  return `M ${point(start)} A ${radius} ${radius} 0 ${end - start > 180 ? 1 : 0} 1 ${point(end)}`;
}

/**
 * EZO's presence: the robot face inside a calm orb whose light and motion show
 * what EZO is doing. Original EZO design (SVG + framer-motion); see
 * docs/OPEN_SOURCE_AUDIT.md for the projects that were studied for ideas.
 */
export function EzoPresence({ state, size = 260, label, className }: EzoPresenceProps) {
  const reduce = useReducedMotion() ?? false;
  const animate = !reduce;
  const look = presenceLook(state);
  const tone = TONE_VAR[look.tone];

  return (
    <div
      className={cn("relative flex flex-col items-center", className)}
      data-testid="ezo-presence"
      data-state={state}
      aria-busy={look.busy}
    >
      <motion.div
        className="relative"
        style={{ width: size, height: size }}
        animate={animate && state === "error" ? { x: [0, -5, 5, -3, 3, 0] } : undefined}
        transition={{ duration: 0.5 }}
      >
        {/* Breathing light */}
        <motion.div
          className="absolute inset-[6%] rounded-full"
          style={{ background: `radial-gradient(circle, ${tone} 0%, transparent 68%)`, filter: `blur(${Math.round(size / 9)}px)` }}
          animate={animate ? { opacity: look.busy ? [0.28, 0.5, 0.28] : [0.14, 0.26, 0.14] } : { opacity: 0.2 }}
          transition={pulse(look.busy ? 1.8 : 5)}
        />

        <svg viewBox="0 0 200 200" width={size} height={size} className="absolute inset-0 overflow-visible" aria-hidden>
          {/* Outer rings: always present, speed shows how busy EZO is. */}
          <motion.circle
            cx={C} cy={C} r={97} fill="none" strokeWidth={0.7} strokeDasharray="1.5 6"
            style={{ stroke: tone, transformOrigin: "100px 100px" }} strokeOpacity={0.45}
            animate={animate ? { rotate: 360 } : undefined}
            transition={spinForever(look.spin)}
          />
          <motion.circle
            cx={C} cy={C} r={91} fill="none" strokeWidth={0.6} strokeDasharray="36 10 3 10"
            style={{ stroke: "var(--accent-2)", transformOrigin: "100px 100px" }} strokeOpacity={0.3}
            animate={animate ? { rotate: -360 } : undefined}
            transition={spinForever(look.spin * 1.5)}
          />

          <StateLayer state={state} tone={tone} animate={animate} spin={look.spin} />
        </svg>

        <div className="absolute inset-[16%]">
          <EzoRobot size={Math.round(size * 0.68)} state={look.face} color={tone} showHalo={false} className="h-full w-full" />
        </div>
      </motion.div>

      {label ? (
        <p
          className={cn(
            "mt-3 text-sm font-medium tracking-wide",
            state === "error" ? "text-danger" : state === "completed" ? "text-success" : "text-ink-muted",
          )}
          aria-live="polite"
          data-testid="ezo-presence-label"
        >
          {label}
        </p>
      ) : null}
    </div>
  );
}

/** The motion that is specific to one state. */
function StateLayer({ state, tone, animate, spin }: { state: EzoState; tone: string; animate: boolean; spin: number }) {
  switch (state) {
    case "recognizing":
    case "listening":
      // Ripples moving outwards: EZO is taking sound in.
      return (
        <g data-layer={state}>
          {[0, 1, 2].map((i) => (
            <motion.circle
              key={i} cx={C} cy={C} r={84} fill="none" strokeWidth={1.2}
              style={{ stroke: tone, transformOrigin: "100px 100px" }}
              initial={{ scale: 0.86, opacity: 0.5 }}
              animate={animate ? { scale: [0.86, 1.18], opacity: [0.5, 0] } : { scale: 1, opacity: 0.35 }}
              transition={animate ? { duration: 2.2, delay: i * 0.73, repeat: Infinity, ease: "easeOut" } : undefined}
            />
          ))}
        </g>
      );
    case "speaking":
      // Waveform around the ring: EZO's voice.
      return (
        <g data-layer="speaking">
          {Array.from({ length: 40 }, (_, i) => (
            <g key={i} transform={`rotate(${i * 9} ${C} ${C})`}>
              <motion.rect
                x={C - 0.9} y={4} width={1.8} height={7} rx={0.9}
                style={{ fill: tone, transformOrigin: "100px 11px" }}
                opacity={0.75}
                animate={animate ? { scaleY: [0.4, 1 + (i % 5) * 0.25, 0.5, 1.2, 0.4] } : { scaleY: 0.8 }}
                transition={animate ? pulse(0.9 + (i % 4) * 0.15, (i % 7) * 0.05) : undefined}
              />
            </g>
          ))}
        </g>
      );
    case "searching":
      // A radar sweep: EZO is looking through files and the web.
      return (
        <motion.g
          data-layer="searching" style={{ transformOrigin: "100px 100px" }}
          animate={animate ? { rotate: 360 } : undefined} transition={spinForever(2.4)}
        >
          <path d={arc(94, 0, 70)} fill="none" strokeWidth={3} strokeLinecap="round" style={{ stroke: tone }} opacity={0.85} />
          <path d={arc(94, 70, 110)} fill="none" strokeWidth={3} strokeLinecap="round" style={{ stroke: tone }} opacity={0.25} />
        </motion.g>
      );
    case "reading":
      // Three points travelling along the ring like eyes along a line.
      return (
        <motion.g
          data-layer="reading" style={{ transformOrigin: "100px 100px" }}
          animate={animate ? { rotate: 360 } : undefined} transition={spinForever(4)}
        >
          {[0, 14, 28].map((offset, i) => {
            const rad = ((offset - 90) * Math.PI) / 180;
            return (
              <circle
                key={offset} cx={C + 94 * Math.cos(rad)} cy={C + 94 * Math.sin(rad)} r={2.6 - i * 0.6}
                style={{ fill: tone }} opacity={1 - i * 0.25}
              />
            );
          })}
        </motion.g>
      );
    case "coding":
      // Segments lighting up in sequence, like a build running.
      return (
        <g data-layer="coding">
          {Array.from({ length: 12 }, (_, i) => (
            <motion.path
              key={i} d={arc(94, i * 30 + 4, i * 30 + 24)} fill="none" strokeWidth={2.4} strokeLinecap="round"
              style={{ stroke: tone }}
              initial={{ opacity: 0.15 }}
              animate={animate ? { opacity: [0.15, 0.9, 0.15] } : { opacity: 0.5 }}
              transition={animate ? pulse(1.8, i * 0.15) : undefined}
            />
          ))}
        </g>
      );
    case "creating":
      // Sparks orbiting at different distances.
      return (
        <motion.g
          data-layer="creating" style={{ transformOrigin: "100px 100px" }}
          animate={animate ? { rotate: 360 } : undefined} transition={spinForever(spin)}
        >
          {[0, 60, 120, 180, 240, 300].map((deg, i) => {
            const radius = 86 + (i % 3) * 5;
            const rad = ((deg - 90) * Math.PI) / 180;
            return (
              <motion.circle
                key={deg} cx={C + radius * Math.cos(rad)} cy={C + radius * Math.sin(rad)} r={1.8}
                style={{ fill: i % 2 ? tone : "var(--accent)" }}
                animate={animate ? { opacity: [0.2, 1, 0.2], r: [1.2, 2.6, 1.2] } : { opacity: 0.7 }}
                transition={animate ? pulse(1.6, i * 0.2) : undefined}
              />
            );
          })}
        </motion.g>
      );
    case "working":
    case "thinking":
      // A steady arc travelling around: EZO is busy.
      return (
        <motion.g
          data-layer={state} style={{ transformOrigin: "100px 100px" }}
          animate={animate ? { rotate: 360 } : undefined} transition={spinForever(state === "working" ? 1.6 : 3)}
        >
          <path
            d={arc(94, 0, state === "working" ? 100 : 40)} fill="none" strokeWidth={2.2} strokeLinecap="round"
            style={{ stroke: tone }} opacity={0.8}
          />
        </motion.g>
      );
    case "completed":
      // The ring closes once.
      return (
        <motion.circle
          data-layer="completed" cx={C} cy={C} r={94} fill="none" strokeWidth={2.4} strokeLinecap="round"
          style={{ stroke: tone, rotate: -90, transformOrigin: "100px 100px" }}
          initial={{ pathLength: animate ? 0 : 1, opacity: 0.9 }}
          animate={{ pathLength: 1, opacity: animate ? [0.9, 0.9, 0.4] : 0.6 }}
          transition={{ duration: 1.2, ease: "easeOut" }}
        />
      );
    case "offline":
    case "error":
      return (
        <circle data-layer={state} cx={C} cy={C} r={94} fill="none" strokeWidth={1.6} strokeDasharray="10 6" style={{ stroke: tone }} opacity={0.7} />
      );
    case "idle":
      return null;
  }
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
