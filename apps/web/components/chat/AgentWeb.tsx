"use client";

import type { AgentRun } from "@ezo/shared";
import { useReducedMotion } from "framer-motion";

/**
 * The run as a constellation: EZO at the centre, the agent that answered, the provider
 * route, and every real step the server recorded, lit by how it ended. Nothing here is
 * invented: a node exists only because the trace lists it. Decorative (aria-hidden); the
 * step list below it is the accessible version. Pattern (core + orbiting helpers +
 * flowing motes) adapted from the MIT APEX-UI reasoning web; original drawing.
 */
const W = 360;
const H = 220;
const CX = W / 2;
const CY = H / 2 + 6;

export function AgentWeb({ run }: { run: AgentRun }) {
  const reduced = useReducedMotion();
  const steps = run.steps.slice(0, 12);
  const nodes = [
    ...(run.agent ? [{ id: `agent:${run.agent}`, label: run.agent, kind: "agent" as const, ok: run.status !== "failed" }] : []),
    ...(run.provider ? [{ id: `route:${run.provider}`, label: `${run.provider}/${run.model ?? ""}`, kind: "route" as const, ok: run.attempts.some((a) => a.status === "ok") }] : []),
    ...steps.map((step, index) => ({ id: `step:${index}`, label: step.name, kind: "step" as const, ok: step.status !== "error" && step.status !== "failed" })),
  ];
  const radius = 78;
  const placed = nodes.map((node, index) => {
    const angle = -Math.PI / 2 + (index / Math.max(1, nodes.length)) * Math.PI * 2;
    const r = node.kind === "step" ? radius : radius * 0.62;
    return { ...node, x: CX + Math.cos(angle) * r * 1.55, y: CY + Math.sin(angle) * r };
  });
  const colour = (node: (typeof placed)[number]) => (!node.ok ? "var(--danger)" : node.kind === "step" ? "var(--accent)" : "var(--accent-2)");

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" aria-hidden="true" data-testid="agent-web" data-nodes={placed.length}>
      <defs>
        <filter id="agent-web-glow" x="-60%" y="-60%" width="220%" height="220%">
          <feGaussianBlur stdDeviation="2.2" result="b" />
          <feMerge>
            <feMergeNode in="b" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>
      {[46, 92, 138].map((r) => (
        <ellipse key={r} cx={CX} cy={CY} rx={r * 1.5} ry={r * 0.95} fill="none" stroke="var(--line)" strokeDasharray="1 6" opacity={0.6} />
      ))}
      {placed.map((node, index) => (
        <g key={node.id}>
          <line x1={CX} y1={CY} x2={node.x} y2={node.y} stroke={colour(node)} strokeOpacity={0.35} strokeWidth={1} />
          {!reduced && node.ok ? (
            <circle r={1.8} fill={colour(node)} filter="url(#agent-web-glow)">
              <animateMotion dur={`${2.4 + (index % 4) * 0.5}s`} repeatCount="indefinite" path={`M${CX} ${CY} L${node.x} ${node.y}`} />
            </circle>
          ) : null}
        </g>
      ))}
      {placed.map((node) => (
        <g key={`${node.id}-node`} data-node={node.kind} data-ok={node.ok}>
          <circle cx={node.x} cy={node.y} r={node.kind === "step" ? 5 : 7} fill={colour(node)} opacity={0.9} filter="url(#agent-web-glow)" />
          <text
            x={node.x}
            y={node.y + (node.y < CY ? -10 : 16)}
            textAnchor="middle"
            fontSize={9}
            fontFamily="ui-monospace, monospace"
            fill="var(--ink-muted)"
          >
            {node.label.length > 22 ? `${node.label.slice(0, 21)}…` : node.label}
          </text>
        </g>
      ))}
      <circle cx={CX} cy={CY} r={18} fill="var(--accent)" opacity={0.12} filter="url(#agent-web-glow)" />
      <circle cx={CX} cy={CY} r={10} fill="none" stroke="var(--accent-2)" strokeWidth={1.2} opacity={0.8} />
      <circle cx={CX} cy={CY} r={4} fill={run.status === "failed" ? "var(--danger)" : "var(--accent-2)"} filter="url(#agent-web-glow)" />
      <text x={CX} y={CY + 30} textAnchor="middle" fontSize={10} fill="var(--ink-muted)" letterSpacing="0.2em">
        EZO
      </text>
    </svg>
  );
}
