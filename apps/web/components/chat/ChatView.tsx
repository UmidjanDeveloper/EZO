"use client";

import type { Message, Project } from "@ezo/shared";
import { ApiError } from "@ezo/shared";
import { Badge, Button, Spinner } from "@ezo/ui";
import { FolderKanban, ScrollText, WifiOff } from "lucide-react";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { useApp } from "@/lib/app-state";
import { useI18n } from "@/lib/i18n/context";
import { Composer } from "./Composer";
import { EmptyState } from "./EmptyState";
import { MessageBubble } from "./MessageBubble";
import { TracePanel } from "./TracePanel";
import type { UiMessage } from "./types";

function fromApi(message: Message): UiMessage {
  return {
    id: message.id,
    role: message.role,
    content: message.content,
    agent: message.agent,
    runId: message.agent_run_id,
    metadata: message.metadata,
  };
}

function errorOf(error: unknown): UiMessage["error"] {
  if (error instanceof ApiError) return { code: error.code, message: error.message, hint: error.hint };
  return { code: "unknown", message: String(error) };
}

interface ChatViewProps {
  conversationId?: string;
  projectId?: string;
}

export function ChatView({ conversationId: initialId, projectId }: ChatViewProps) {
  const { m } = useI18n();
  const { status, refreshConversations, showDebug, setShowDebug } = useApp();
  const pathname = usePathname();

  const [conversationId, setConversationId] = useState<string | undefined>(initialId);
  const [title, setTitle] = useState<string>("");
  const [project, setProject] = useState<Project | null>(null);
  const [messages, setMessages] = useState<UiMessage[]>([]);
  const [loading, setLoading] = useState(Boolean(initialId));
  const [loadError, setLoadError] = useState<UiMessage["error"] | null>(null);
  const [streaming, setStreaming] = useState(false);
  const [traceRunId, setTraceRunId] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const stickToBottom = useRef(true);

  // Load an existing conversation.
  useEffect(() => {
    if (!initialId) return;
    let cancelled = false;
    setLoading(true);
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

  // Keep the newest message in view while streaming, unless the user scrolled up.
  useEffect(() => {
    const element = scrollRef.current;
    if (element && stickToBottom.current) element.scrollTop = element.scrollHeight;
  }, [messages]);

  const onScroll = useCallback(() => {
    const element = scrollRef.current;
    if (!element) return;
    stickToBottom.current = element.scrollHeight - element.scrollTop - element.clientHeight < 80;
  }, []);

  const updateLast = useCallback((patch: (message: UiMessage) => UiMessage) => {
    setMessages((current) => {
      if (current.length === 0) return current;
      const next = current.slice();
      next[next.length - 1] = patch(next[next.length - 1]!);
      return next;
    });
  }, []);

  const send = useCallback(
    async (text: string) => {
      if (streaming) return;
      const controller = new AbortController();
      abortRef.current = controller;
      stickToBottom.current = true;
      setStreaming(true);
      setMessages((current) => [
        ...current,
        { id: `local-user-${Date.now()}`, role: "user", content: text },
        { id: `local-assistant-${Date.now()}`, role: "assistant", content: "", streaming: true },
      ]);

      try {
        const stream = api.streamChat(
          { message: text, conversation_id: conversationId ?? null, project_id: conversationId ? null : projectId },
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
            updateLast((message) => ({
              ...message,
              agent: meta.agent,
              runId: meta.run_id,
              metadata: {
                requested_agent: meta.requested_agent,
                requested_agent_available: meta.requested_agent_available,
              },
            }));
          } else if (event.type === "delta") {
            const chunk = event.data.text;
            updateLast((message) => ({ ...message, content: message.content + chunk }));
          } else if (event.type === "done") {
            const final = fromApi(event.data.message);
            updateLast(() => ({ ...final, streaming: false }));
          } else if (event.type === "error") {
            const error = event.data;
            updateLast((message) => ({ ...message, streaming: false, error, runId: error.run_id }));
          }
        }
      } catch (error) {
        if (controller.signal.aborted) {
          updateLast((message) => ({ ...message, streaming: false }));
        } else {
          updateLast((message) => ({ ...message, streaming: false, error: errorOf(error) }));
        }
      } finally {
        updateLast((message) => ({ ...message, streaming: false }));
        setStreaming(false);
        abortRef.current = null;
        void refreshConversations();
      }
    },
    [conversationId, projectId, refreshConversations, streaming, updateLast],
  );

  const stop = useCallback(() => abortRef.current?.abort(), []);

  const offline = status?.offline_mode;
  const empty = !loading && messages.length === 0;

  return (
    <div className="flex h-full flex-col">
      <div className="flex min-h-12 items-center gap-2 border-b border-line px-4 py-2">
        <h1 className="min-w-0 flex-1 truncate text-sm font-medium" data-testid="chat-title">
          {title || m.common.newChat}
        </h1>
        {project ? (
          <Badge tone="accent">
            <FolderKanban size={12} /> {project.name}
          </Badge>
        ) : null}
        {status?.debug_traces ? (
          <Button
            variant={showDebug ? "secondary" : "ghost"}
            size="sm"
            icon={<ScrollText size={14} />}
            onClick={() => setShowDebug(!showDebug)}
            aria-pressed={showDebug}
            data-testid="toggle-debug"
          >
            <span className="hidden sm:inline">{m.chat.debug}</span>
          </Button>
        ) : null}
      </div>

      {offline ? (
        <div className="mx-3 mt-3 flex items-start gap-2 rounded-xl border border-warning/40 bg-warning/5 px-4 py-2.5 text-sm sm:mx-auto sm:w-full sm:max-w-3xl" data-testid="offline-banner">
          <WifiOff size={16} className="mt-0.5 shrink-0 text-warning" />
          <p>
            <span className="font-medium">{m.chat.offlineTitle}.</span>{" "}
            <span className="text-ink-muted">{m.chat.offlineBody}</span>
          </p>
        </div>
      ) : null}

      <div ref={scrollRef} onScroll={onScroll} className="flex min-h-0 flex-1 flex-col overflow-y-auto">
        {loading ? (
          <div className="flex flex-1 items-center justify-center">
            <Spinner label={m.common.loading} />
          </div>
        ) : loadError ? (
          <div className="flex flex-1 items-center justify-center px-4 text-center">
            <div>
              <p className="font-medium text-danger">{loadError.message}</p>
              {loadError.hint ? <p className="mt-1 text-sm text-ink-muted">{loadError.hint}</p> : null}
            </div>
          </div>
        ) : empty ? (
          <EmptyState onPick={(text) => void send(text)} />
        ) : (
          <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-4 py-6">
            {messages.map((message) => (
              <MessageBubble key={message.id} message={message} onShowTrace={setTraceRunId} />
            ))}
          </div>
        )}
      </div>

      <Composer streaming={streaming} onSend={(text) => void send(text)} onStop={stop} autoFocus />
      <TracePanel runId={traceRunId} onClose={() => setTraceRunId(null)} />
    </div>
  );
}
