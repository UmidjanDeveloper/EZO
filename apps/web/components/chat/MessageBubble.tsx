"use client";

import { Badge, cn } from "@ezo/ui";
import { motion } from "framer-motion";
import { AlertTriangle, Brain, Check, Copy, Info, ScrollText } from "lucide-react";
import { useState } from "react";
import { useApp } from "@/lib/app-state";
import { useI18n } from "@/lib/i18n/context";
import { EzoOrb } from "../common/EzoOrb";
import { Markdown } from "./Markdown";
import type { UiMessage } from "./types";

interface Props {
  message: UiMessage;
  onShowTrace?: (runId: string) => void;
}

export function MessageBubble({ message, onShowTrace }: Props) {
  const { m, f, language } = useI18n();
  const { status, showDebug } = useApp();
  const [copied, setCopied] = useState(false);

  if (message.role === "user") {
    return (
      <motion.div
        className="flex justify-end"
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        data-testid="message-user"
      >
        <div className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-md bg-surface-2 px-4 py-2.5 text-[15px] leading-relaxed">
          {message.content}
        </div>
      </motion.div>
    );
  }

  const meta = message.metadata ?? {};
  const requested = meta.requested_agent;
  const requestedInfo = status?.agents.find((agent) => agent.key === requested);
  const showFallback = requested && meta.requested_agent_available === false && requestedInfo;

  async function copy() {
    try {
      await navigator.clipboard.writeText(message.content);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  }

  return (
    <motion.div
      className="flex gap-3"
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      data-testid="message-assistant"
    >
      <EzoOrb size={28} active={message.streaming} className="mt-0.5 shrink-0" />
      <div className="min-w-0 flex-1">
        {showFallback ? (
          <p className="mb-2 flex items-start gap-1.5 text-xs text-ink-muted" data-testid="agent-fallback">
            <Info size={14} className="mt-px shrink-0 text-accent-2" />
            {f(m.chat.agentFallback, {
              agent: requestedInfo.names[language],
              milestone: requestedInfo.milestone,
            })}
          </p>
        ) : null}

        {message.error ? (
          <div className="rounded-xl border border-danger/40 bg-danger/5 px-4 py-3 text-sm" role="alert">
            <p className="flex items-center gap-2 font-medium text-danger">
              <AlertTriangle size={16} /> {m.chat.errorTitle}
            </p>
            <p className="mt-1 text-ink">{message.error.message}</p>
            {message.error.hint ? <p className="mt-1 text-ink-muted">{message.error.hint}</p> : null}
          </div>
        ) : message.content ? (
          <div className="text-[15px]">
            <Markdown text={message.content} />
            {message.streaming ? (
              <span className="ml-0.5 inline-block h-4 w-1.5 animate-pulse rounded-sm bg-accent align-middle" />
            ) : null}
          </div>
        ) : (
          <p className="animate-pulse text-sm text-ink-muted">{m.chat.thinking}</p>
        )}

        {!message.streaming && (message.content || message.error) ? (
          <div className="mt-2 flex flex-wrap items-center gap-1.5 text-xs text-ink-faint">
            {message.agent ? <Badge>{message.agent}</Badge> : null}
            {meta.model ? <span className={cn("font-mono")}>{meta.model}</span> : null}
            {meta.memories_saved ? (
              <Badge tone="accent">
                <Brain size={12} /> {m.chat.memorySaved}
              </Badge>
            ) : null}
            {message.content ? (
              <button
                type="button"
                onClick={() => void copy()}
                className="rounded p-1 hover:text-ink"
                aria-label={copied ? m.chat.copied : m.chat.copy}
                title={copied ? m.chat.copied : m.chat.copy}
              >
                {copied ? <Check size={14} /> : <Copy size={14} />}
              </button>
            ) : null}
            {showDebug && message.runId && onShowTrace ? (
              <button
                type="button"
                onClick={() => onShowTrace(message.runId!)}
                className="flex items-center gap-1 rounded px-1 py-0.5 hover:text-ink"
                data-testid="show-trace"
              >
                <ScrollText size={14} /> {m.chat.debug}
              </button>
            ) : null}
          </div>
        ) : null}
      </div>
    </motion.div>
  );
}
