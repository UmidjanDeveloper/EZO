"use client";

import { Badge, cn, Spinner } from "@ezo/ui";
import { AudioLines, FolderKanban, MessageSquare, WifiOff } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useApp } from "@/lib/app-state";
import { useI18n } from "@/lib/i18n/context";
import { HistoryButton } from "../layout/shell-context";
import { EzoStatus } from "../robot/EzoPresence";
import { AttachmentList, useAttachments } from "./Attachments";
import { Composer } from "./Composer";
import { EmptyState } from "./EmptyState";
import { MessageBubble } from "./MessageBubble";
import { TracePanel } from "./TracePanel";
import { useChatSession } from "./useChatSession";
import { VoiceStage } from "./VoiceStage";

interface ChatViewProps {
  conversationId?: string;
  projectId?: string;
}

type Mode = "text" | "voice";

export function ChatView({ conversationId, projectId }: ChatViewProps) {
  const { m } = useI18n();
  const { status } = useApp();
  const session = useChatSession({ conversationId, projectId });
  const { title, project, messages, loading, loadError, streaming, presence, send, stop } = session;

  const attachments = useAttachments(project?.id ?? projectId);
  const [mode, setMode] = useState<Mode>("text");
  const [traceRunId, setTraceRunId] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const stickToBottom = useRef(true);

  // Keep the newest message in view while streaming, unless the user scrolled up.
  useEffect(() => {
    const element = scrollRef.current;
    if (element && stickToBottom.current) element.scrollTop = element.scrollHeight;
  }, [messages, mode]);

  const onScroll = useCallback(() => {
    const element = scrollRef.current;
    if (!element) return;
    stickToBottom.current = element.scrollHeight - element.scrollTop - element.clientHeight < 80;
  }, []);

  const sendText = useCallback(
    (text: string) => {
      stickToBottom.current = true;
      void send(text, "text");
    },
    [send],
  );

  const empty = !loading && messages.length === 0;

  return (
    <div className="flex h-full flex-col">
      <header className="flex h-12 shrink-0 items-center gap-2 px-3">
        <HistoryButton />
        <h1 className="min-w-0 flex-1 truncate text-sm text-ink-muted" data-testid="chat-title">
          {title}
        </h1>
        {mode === "text" ? <EzoStatus state={presence} label={m.presence[presence]} /> : null}
        {project ? (
          <Badge tone="accent">
            <FolderKanban size={12} /> {project.name}
          </Badge>
        ) : null}
        <div className="flex rounded-full border border-line bg-surface p-0.5" role="tablist" aria-label="EZO">
          {(
            [
              { key: "text", label: m.voice.modeText, icon: MessageSquare },
              { key: "voice", label: m.voice.modeVoice, icon: AudioLines },
            ] as const
          ).map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              type="button"
              role="tab"
              aria-selected={mode === key}
              onClick={() => setMode(key)}
              data-testid={`mode-${key}`}
              className={cn(
                "flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium transition-colors",
                mode === key ? "bg-accent text-on-accent" : "text-ink-muted hover:text-ink",
              )}
            >
              <Icon size={14} />
              <span className="hidden sm:inline">{label}</span>
            </button>
          ))}
        </div>
      </header>

      {status?.offline_mode ? (
        <div
          className="mx-3 flex items-start gap-2 rounded-xl border border-warning/40 bg-warning/5 px-4 py-2.5 text-sm sm:mx-auto sm:w-full sm:max-w-3xl"
          data-testid="offline-banner"
        >
          <WifiOff size={16} className="mt-0.5 shrink-0 text-warning" />
          <p>
            <span className="font-medium">{m.chat.offlineTitle}.</span>{" "}
            <span className="text-ink-muted">{m.chat.offlineBody}</span>
          </p>
        </div>
      ) : null}

      {mode === "voice" ? (
        <div className="min-h-0 flex-1">
          <VoiceStage session={session} />
        </div>
      ) : (
        <>
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
              <EmptyState onPick={sendText} />
            ) : (
              <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-4 py-6">
                {messages.map((message) => (
                  <MessageBubble key={message.id} message={message} onShowTrace={setTraceRunId} />
                ))}
              </div>
            )}
          </div>
          <Composer
            streaming={streaming}
            onSend={sendText}
            onStop={stop}
            onVoice={() => setMode("voice")}
            onAttach={attachments.attach}
            above={<AttachmentList items={attachments.items} onDismiss={attachments.dismiss} />}
            autoFocus
          />
        </>
      )}
      <TracePanel runId={traceRunId} onClose={() => setTraceRunId(null)} />
    </div>
  );
}
