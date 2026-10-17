"use client";

import { Badge } from "@ezo/ui";
import { motion } from "framer-motion";
import { AlertTriangle, Brain, Check, Copy, Mic, ScrollText, Volume2 } from "lucide-react";
import { useState } from "react";
import { useApp } from "@/lib/app-state";
import { useI18n } from "@/lib/i18n/context";
import { speak, speechSynthesisSupported, toSpeakableText } from "@/lib/speech";
import { EzoRobot } from "../robot/EzoRobot";
import { Markdown } from "./Markdown";
import { Sources } from "./Sources";
import type { UiMessage } from "./types";

interface Props {
  message: UiMessage;
  onShowTrace?: (runId: string) => void;
}

export function MessageBubble({ message, onShowTrace }: Props) {
  const { m, language } = useI18n();
  const { showDebug } = useApp();
  const [copied, setCopied] = useState(false);

  if (message.role === "user") {
    return (
      <motion.div className="flex justify-end" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}>
        <div
          className="flex max-w-[85%] items-start gap-2 whitespace-pre-wrap rounded-2xl rounded-br-md bg-surface-2 px-4 py-2.5 text-[15px] leading-relaxed"
          data-testid="message-user"
        >
          {message.metadata?.channel === "voice" ? (
            <Mic size={14} className="mt-1 shrink-0 text-accent" aria-hidden />
          ) : null}
          <span>{message.content}</span>
        </div>
      </motion.div>
    );
  }

  const robotState = message.streaming ? (message.content ? "speaking" : "thinking") : "idle";

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
    <motion.div className="flex gap-3" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} data-testid="message-assistant">
      <EzoRobot size={34} state={robotState} showHalo={false} className="mt-0.5 shrink-0" />
      <div className="min-w-0 flex-1">
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
          <p className="animate-pulse pt-1.5 text-sm text-ink-muted">{m.chat.thinking}</p>
        )}

        {!message.streaming && message.metadata?.citations?.length ? (
          <Sources citations={message.metadata.citations} />
        ) : null}

        {!message.streaming && message.content && !message.error ? (
          <div className="mt-1.5 flex flex-wrap items-center gap-1 text-xs text-ink-faint">
            <button
              type="button"
              onClick={() => void copy()}
              className="rounded p-1 hover:text-ink"
              aria-label={copied ? m.chat.copied : m.chat.copy}
              title={copied ? m.chat.copied : m.chat.copy}
            >
              {copied ? <Check size={14} /> : <Copy size={14} />}
            </button>
            {speechSynthesisSupported() ? (
              <button
                type="button"
                onClick={() => void speak(toSpeakableText(message.content), message.language ?? language)}
                className="rounded p-1 hover:text-ink"
                aria-label={m.voice.listen}
                title={m.voice.listen}
              >
                <Volume2 size={14} />
              </button>
            ) : null}
            {message.metadata?.memories_saved ? (
              <Badge tone="accent">
                <Brain size={12} /> {m.chat.memorySaved}
              </Badge>
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
