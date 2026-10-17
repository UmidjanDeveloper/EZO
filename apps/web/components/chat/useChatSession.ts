"use client";

import type { ChatChannel, LanguageCode, Message, Project } from "@ezo/shared";
import { ApiError } from "@ezo/shared";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { useApp } from "@/lib/app-state";
import { nextEzoState, SETTLE_AFTER_MS, type EzoEvent, type EzoState } from "@/lib/ezo-state";
import type { UiMessage } from "./types";

export function fromApi(message: Message): UiMessage {
  return {
    id: message.id,
    role: message.role,
    content: message.content,
    agent: message.agent,
    runId: message.agent_run_id,
    metadata: message.metadata,
    language: (message.language as LanguageCode | null) ?? undefined,
  };
}

export function errorOf(error: unknown): NonNullable<UiMessage["error"]> {
  if (error instanceof ApiError) return { code: error.code, message: error.message, hint: error.hint };
  return { code: "unknown", message: String(error) };
}

interface Options {
  conversationId?: string;
  projectId?: string;
}

/**
 * State of one conversation: loading history, sending messages and
 * receiving the streamed reply. Shared by typed chat and voice conversation.
 */
export function useChatSession({ conversationId: initialId, projectId }: Options) {
  const { refreshConversations } = useApp();
  const pathname = usePathname();

  const [conversationId, setConversationId] = useState<string | undefined>(initialId);
  const [title, setTitle] = useState("");
  const [project, setProject] = useState<Project | null>(null);
  const [messages, setMessages] = useState<UiMessage[]>([]);
  const [loading, setLoading] = useState(Boolean(initialId));
  const [loadError, setLoadError] = useState<UiMessage["error"] | null>(null);
  const [streaming, setStreaming] = useState(false);
  const [presence, setPresence] = useState<EzoState>("idle");
  const abortRef = useRef<AbortController | null>(null);

  const signal = useCallback((event: EzoEvent) => setPresence((current) => nextEzoState(current, event)), []);

  // "Done" and "error" stay visible for a moment, then EZO returns to idle.
  useEffect(() => {
    const delay = SETTLE_AFTER_MS[presence];
    if (delay === undefined) return;
    const timer = window.setTimeout(() => signal({ type: "settle" }), delay);
    return () => window.clearTimeout(timer);
  }, [presence, signal]);

  // Load an existing conversation.
  useEffect(() => {
    if (!initialId) return;
    let cancelled = false;
    Promise.all([api.getConversation(initialId), api.listMessages(initialId)])
      .then(([conversation, rows]) => {
        if (cancelled) return;
        setTitle(conversation.title);
        setMessages(rows.map(fromApi));
        if (conversation.project_id) {
          api.getProject(conversation.project_id).then(setProject).catch(() => setProject(null));
        }
      })
      .catch((error: unknown) => !cancelled && setLoadError(errorOf(error)))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [initialId]);

  // A chat started inside a project.
  useEffect(() => {
    if (!projectId || initialId) return;
    api.getProject(projectId).then(setProject).catch(() => setProject(null));
  }, [projectId, initialId]);

  // "New chat" navigates back to "/" while this view may still be mounted (the URL
  // was switched to /chat/<id> with history.replaceState). Reset when the path
  // changes back to "/" — tracked during render, per React's guidance.
  const [lastPathname, setLastPathname] = useState(pathname);
  if (pathname !== lastPathname) {
    setLastPathname(pathname);
    if (pathname === "/" && !initialId && !streaming) {
      setConversationId(undefined);
      setMessages([]);
      setTitle("");
    }
  }

  const updateLast = useCallback((patch: (message: UiMessage) => UiMessage) => {
    setMessages((current) => {
      if (current.length === 0) return current;
      const next = current.slice();
      next[next.length - 1] = patch(next[next.length - 1]!);
      return next;
    });
  }, []);

  /** Send a message; resolves with the final assistant message (or null if stopped). */
  const send = useCallback(
    async (text: string, channel: ChatChannel = "text"): Promise<UiMessage | null> => {
      if (streaming) return null;
      const controller = new AbortController();
      abortRef.current = controller;
      setStreaming(true);
      signal({ type: "send" });
      setMessages((current) => [
        ...current,
        { id: `local-user-${Date.now()}`, role: "user", content: text, metadata: { channel } },
        { id: `local-assistant-${Date.now()}`, role: "assistant", content: "", streaming: true },
      ]);

      let final: UiMessage | null = null;
      try {
        const stream = api.streamChat(
          {
            message: text,
            conversation_id: conversationId ?? null,
            project_id: conversationId ? null : projectId,
            channel,
          },
          controller.signal,
        );
        for await (const event of stream) {
          if (event.type === "meta") {
            const meta = event.data;
            if (!conversationId) {
              setConversationId(meta.conversation_id);
              setTitle(meta.conversation_title);
              window.history.replaceState(null, "", `/chat/${meta.conversation_id}`);
            }
            updateLast((message) => ({ ...message, agent: meta.agent, runId: meta.run_id, language: meta.language }));
          } else if (event.type === "activity") {
            signal({ type: "activity", stage: event.data.stage });
          } else if (event.type === "delta") {
            signal({ type: "delta" });
            const chunk = event.data.text;
            updateLast((message) => ({ ...message, content: message.content + chunk }));
          } else if (event.type === "done") {
            signal({ type: "done" });
            final = { ...fromApi(event.data.message), streaming: false };
            const done = final;
            updateLast(() => done);
          } else {
            const error = event.data;
            signal({ type: "error" });
            final = null;
            updateLast((message) => ({ ...message, streaming: false, error, runId: error.run_id }));
          }
        }
      } catch (error) {
        if (!controller.signal.aborted) {
          signal({ type: "error" });
          updateLast((message) => ({ ...message, streaming: false, error: errorOf(error) }));
        }
      } finally {
        signal({ type: "stopped" });
        updateLast((message) => ({ ...message, streaming: false }));
        setStreaming(false);
        abortRef.current = null;
        void refreshConversations();
      }
      return final;
    },
    [conversationId, projectId, refreshConversations, signal, streaming, updateLast],
  );

  const stop = useCallback(() => abortRef.current?.abort(), []);

  return { conversationId, title, project, messages, loading, loadError, streaming, presence, send, stop };
}
