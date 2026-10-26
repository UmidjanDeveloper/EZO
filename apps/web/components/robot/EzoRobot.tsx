"use client";

import { motion, useReducedMotion, type Transition } from "framer-motion";
import { useId } from "react";
import { cn } from "@ezo/ui";

export type RobotState = "idle" | "listening" | "thinking" | "speaking";

interface EzoRobotProps {
  size?: number;
  state?: RobotState;
  className?: string;
  /** Decorative halo rings and floating motion (off for tiny avatars). */
  showHalo?: boolean;
  /** Overrides the light colour (e.g. success / danger from EzoPresence). */
  color?: string;
  /** Accessible name in the UI language; without one the robot is decorative (its parent names it). */
  label?: string;
}

const EYE_COLOR: Record<RobotState, string> = {
  idle: "var(--accent)",
  listening: "var(--accent)",
  thinking: "var(--accent-2)",
  speaking: "var(--accent)",
};

const loop = (duration: number, extra: Transition = {}): Transition => ({
  duration,
  repeat: Infinity,
  ease: "easeInOut",
  ...extra,
});

/**
 * EZO's face: a calm, futuristic robot whose eyes, mouth and core light
 * react to what EZO is doing (idle, listening, thinking, speaking).
 */
export function EzoRobot({ size = 240, state = "idle", className, showHalo = true, color, label }: EzoRobotProps) {
  const reduce = useReducedMotion() ?? false;
  const uid = useId().replace(/:/g, "");
  const id = (name: string) => `${name}-${uid}`;
  const eye = color ?? EYE_COLOR[state];
  const animate = !reduce;

  // Eyes: blink when idle, widen when listening, look around when thinking.
  const eyeAnimation =
    !animate
      ? {}
      : state === "listening"
        ? { scaleY: [1.1, 1.25, 1.1], scaleX: [1.05, 1.12, 1.05] }
        : state === "thinking"
          ? { x: [-5, 5, 5, -5, -5], scaleY: [1, 1, 0.9, 1, 1] }
          : state === "speaking"
            ? { scaleY: [0.75, 0.9, 0.75] }
            : { scaleY: [1, 1, 0.08, 1, 1] };
  const eyeTransition =
    state === "listening"
      ? loop(1.2)
      : state === "thinking"
        ? loop(2.4)
        : state === "speaking"
          ? loop(0.9)
          : loop(4.5, { times: [0, 0.9, 0.94, 0.98, 1] });

  const mouthBars = [0, 1, 2, 3, 4];

  return (
    <motion.div
      className={cn("relative select-none", className)}
      style={{ width: size, height: size }}
      animate={animate && showHalo ? { y: [0, -6, 0] } : undefined}
      transition={loop(5)}
      role={label ? "img" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      data-testid="ezo-robot"
      data-state={state}
    >
      {/* Soft glow behind the robot. */}
      <motion.div
        className="absolute inset-[12%] rounded-full"
        style={{
          background: `radial-gradient(circle, ${eye} 0%, transparent 70%)`,
          filter: `blur(${Math.max(6, Math.round(size / 10))}px)`,
        }}
        animate={animate ? { opacity: state === "idle" ? [0.25, 0.4, 0.25] : [0.4, 0.7, 0.4] } : { opacity: 0.35 }}
        transition={loop(state === "idle" ? 4 : 1.4)}
      />

      <svg viewBox="0 0 200 200" width={size} height={size} className="relative overflow-visible">
        <defs>
          <linearGradient id={id("shell")} x1="0" y1="0" x2="0.3" y2="1">
            <stop offset="0%" style={{ stopColor: "var(--robot-shell-1)" }} />
            <stop offset="100%" style={{ stopColor: "var(--robot-shell-2)" }} />
          </linearGradient>
          <linearGradient id={id("visor")} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" style={{ stopColor: "var(--robot-visor)" }} />
            <stop offset="100%" style={{ stopColor: "var(--robot-visor)", stopOpacity: 0.85 }} />
          </linearGradient>
          <linearGradient id={id("sheen")} x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#ffffff" stopOpacity="0.35" />
            <stop offset="45%" stopColor="#ffffff" stopOpacity="0" />
          </linearGradient>
          <filter id={id("glow")} x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="2.5" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
          <clipPath id={id("visorClip")}>
            <rect x="56" y="64" width="88" height="54" rx="26" />
          </clipPath>
        </defs>

        {/* Halo rings */}
        {showHalo ? (
          <>
            <motion.circle
              cx="100" cy="100" r="96" fill="none"
              style={{ stroke: eye, transformOrigin: "100px 100px" }}
              strokeOpacity="0.28" strokeWidth="0.8" strokeDasharray="2 7"
              animate={animate ? { rotate: 360 } : undefined}
              transition={{ duration: state === "thinking" ? 8 : 40, repeat: Infinity, ease: "linear" }}
            />
            <motion.circle
              cx="100" cy="100" r="88" fill="none"
              style={{ stroke: "var(--accent-2)", transformOrigin: "100px 100px" }}
              strokeOpacity="0.22" strokeWidth="0.6" strokeDasharray="40 14 4 14"
              animate={animate ? { rotate: -360 } : undefined}
              transition={{ duration: state === "thinking" ? 10 : 60, repeat: Infinity, ease: "linear" }}
            />
            {state === "listening" && animate ? (
              <motion.circle
                cx="100" cy="100" r="80" fill="none"
                style={{ stroke: eye, transformOrigin: "100px 100px" }}
                strokeWidth="1.2"
                initial={{ scale: 0.8, opacity: 0.6 }}
                animate={{ scale: 1.2, opacity: 0 }}
                transition={{ duration: 1.6, repeat: Infinity, ease: "easeOut" }}
              />
            ) : null}
          </>
        ) : null}

        {/* Shoulders */}
        <path
          d="M40 196 C40 168 64 156 100 156 C136 156 160 168 160 196 Z"
          fill={`url(#${id("shell")})`}
          style={{ stroke: "var(--robot-shell-edge)" }}
          strokeWidth="1"
        />
        <rect x="88" y="138" width="24" height="20" rx="6" style={{ fill: "var(--robot-shell-2)" }} />
        {/* Chest core */}
        <motion.circle
          cx="100" cy="178" r="7"
          style={{ fill: eye }}
          filter={`url(#${id("glow")})`}
          animate={animate ? { opacity: state === "idle" ? [0.5, 0.9, 0.5] : [0.7, 1, 0.7] } : undefined}
          transition={loop(state === "idle" ? 3 : 0.8)}
        />

        {/* Antenna */}
        <line x1="100" y1="40" x2="100" y2="22" style={{ stroke: "var(--robot-shell-edge)" }} strokeWidth="3" strokeLinecap="round" />
        <motion.circle
          cx="100" cy="18" r="5.5"
          style={{ fill: eye }}
          filter={`url(#${id("glow")})`}
          animate={animate ? { opacity: [0.55, 1, 0.55] } : undefined}
          transition={loop(state === "idle" ? 2.5 : 0.7)}
        />

        {/* Ear pods */}
        <rect x="32" y="80" width="16" height="42" rx="8" fill={`url(#${id("shell")})`} style={{ stroke: "var(--robot-shell-edge)" }} strokeWidth="1" />
        <rect x="152" y="80" width="16" height="42" rx="8" fill={`url(#${id("shell")})`} style={{ stroke: "var(--robot-shell-edge)" }} strokeWidth="1" />
        <rect x="37" y="94" width="6" height="14" rx="3" style={{ fill: eye }} opacity="0.6" />
        <rect x="157" y="94" width="6" height="14" rx="3" style={{ fill: eye }} opacity="0.6" />

        {/* Head */}
        <rect x="44" y="38" width="112" height="108" rx="42" fill={`url(#${id("shell")})`} style={{ stroke: "var(--robot-shell-edge)" }} strokeWidth="1.2" />
        <rect x="44" y="38" width="112" height="108" rx="42" fill={`url(#${id("sheen")})`} />

        {/* Visor */}
        <rect x="56" y="64" width="88" height="54" rx="26" fill={`url(#${id("visor")})`} />
        <rect x="56" y="64" width="88" height="54" rx="26" fill="none" style={{ stroke: eye }} strokeOpacity="0.35" strokeWidth="1" />
        <g clipPath={`url(#${id("visorClip")})`}>
          {state === "thinking" && animate ? (
            <motion.rect
              y="64" width="10" height="54"
              style={{ fill: "var(--accent-2)" }}
              opacity="0.25"
              initial={{ x: 50 }}
              animate={{ x: [50, 140, 50] }}
              transition={loop(1.8)}
            />
          ) : null}
          {/* Eyes */}
          {[82, 118].map((cx) => (
            <motion.rect
              key={cx}
              x={cx - 9} y="80" width="18" height="22" rx="9"
              style={{ fill: eye, transformBox: "fill-box", transformOrigin: "center" }}
              filter={`url(#${id("glow")})`}
              animate={eyeAnimation}
              transition={eyeTransition}
            />
          ))}
          <path d="M60 70 Q100 60 140 70" fill="none" stroke="#ffffff" strokeOpacity="0.12" strokeWidth="3" strokeLinecap="round" />
        </g>

        {/* Mouth: light bars that move while speaking */}
        {mouthBars.map((index) => {
          const x = 87 + index * 6.5;
          const base = state === "speaking" ? 6 : state === "listening" ? 3 : 2;
          return (
            <motion.rect
              key={index}
              x={x} y={127} width="4" height={base} rx="2"
              style={{ fill: eye, transformBox: "fill-box", transformOrigin: "center" }}
              opacity={state === "idle" ? 0.45 : 0.9}
              animate={
                animate && state === "speaking"
                  ? { scaleY: [1, 2.6 - (index % 2) * 0.9, 0.8, 2.1, 1] }
                  : animate && state === "listening"
                    ? { scaleY: [1, 1.6, 1] }
                    : { scaleY: 1 }
              }
              transition={
                state === "speaking"
                  ? loop(0.55 + index * 0.07)
                  : state === "listening"
                    ? loop(1.2, { delay: index * 0.1 })
                    : { duration: 0.2 }
              }
            />
          );
        })}
      </svg>
    </motion.div>
  );
}
