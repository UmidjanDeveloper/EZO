"use client";

import { Badge } from "@ezo/ui";
import { motion } from "framer-motion";
import type { ArtifactRef } from "@ezo/shared";
import { AlertTriangle, Bookmark, BookmarkCheck, Brain, Check, Copy, FileText, Mic, ScrollText, Volume2 } from "lucide-react";
import { useState } from "react";
import { api } from "@/lib/api";
import { useApp } from "@/lib/app-state";
import { useI18n } from "@/lib/i18n/context";
import { speak, speechSynthesisSupported, toSpeakableText } from "@/lib/speech";
import { ArtifactCard } from "../artifacts/ArtifactCard";
import { EnergyMark } from "../robot/EnergyMark";
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
  const [saved, setSaved] = useState<ArtifactRef[]>([]);
  const [saving, setSaving] = useState(false);

  if (message.role === "user") {
    const files = message.metadata?.attachment_names ?? [];
    return (
      <motion.div className="flex flex-col items-end gap-1.5" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}>
        {files.length ? (
          <ul className="flex max-w-[85%] flex-wrap justify-end gap-1.5" aria-label={m.knowledge.attachedFiles} data-testid="message-attachments">
            {files.map((name, index) => (
              <li
                key={`${name}-${index}`}
                className="flex max-w-[14rem] items-center gap-1.5 rounded-lg border border-line bg-surface px-2 py-1 text-xs text-ink-muted"
              >
                <FileText size={12} className="shrink-0" aria-hidden />
                <span className="truncate">{name}</span>
              </li>
            ))}
          </ul>
        ) : null}
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

  const artifacts = [...(message.metadata?.artifacts ?? []), ...saved].filter(
    (artifact, index, all) => all.findIndex((other) => other.id === artifact.id) === index,
  );
  const persisted = !message.id.startsWith("local-");
  const alreadySaved = saved.length > 0 || artifacts.some((artifact) => artifact.type === "document");

  async function saveAsArtifact() {
    setSaving(true);
    try {
      const artifact = await api.createArtifact({
        title: titleFrom(message.content),
        content: message.content,
        message_id: message.id,
      });
      setSaved((current) => [...current, { id: artifact.id, title: artifact.title, type: artifact.type, version: 1 }]);
    } finally {
      setSaving(false);
    }
  }

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
      <EnergyMark size={34} className="mt-0.5" />
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

        {artifacts.map((artifact) => (
          <ArtifactCard key={artifact.id} artifact={artifact} />
        ))}

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
            {persisted ? (
              <button
                type="button"
                onClick={() => void saveAsArtifact()}
                disabled={saving || alreadySaved}
                className="flex items-center gap-1 rounded px-1 py-0.5 hover:text-ink disabled:opacity-60"
                aria-label={alreadySaved ? m.artifacts.saved : m.artifacts.saveAnswer}
                title={alreadySaved ? m.artifacts.saved : m.artifacts.saveAnswer}
                data-testid="save-answer"
              >
                {alreadySaved ? <BookmarkCheck size={14} className="text-accent" /> : <Bookmark size={14} />}
                <span className="hidden sm:inline">{alreadySaved ? m.artifacts.saved : m.artifacts.saveAnswer}</span>
              </button>
            ) : null}
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

/** A short title for a saved answer: its first heading or line. */
export function titleFrom(content: string): string {
  const firstLine = content
    .split("\n")
    .map((line) => line.replace(/^[#>*\-\s\d.]+/, "").replace(/[*_`]/g, "").trim())
    .find(Boolean);
  const title = firstLine ?? "EZO";
  return title.length > 80 ? `${title.slice(0, 77).trimEnd()}…` : title;
}
