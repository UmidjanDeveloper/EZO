"use client";

import type { KnowledgeLibrary } from "@ezo/shared";
import { Badge, cn, Spinner } from "@ezo/ui";
import { AudioLines, BookOpen, ChevronDown, FolderKanban, MessageSquare, WifiOff, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
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
  const { m, f } = useI18n();
  const { status } = useApp();
  const session = useChatSession({ conversationId, projectId });
  const {
    title,
    project,
    libraryId,
    libraryName,
    selectLibrary,
    clearLibrary,
    messages,
    loading,
    loadError,
    streaming,
    presence,
    send,
    stop,
  } = session;

  const [libraries, setLibraries] = useState<KnowledgeLibrary[]>([]);
  const [libraryMenuOpen, setLibraryMenuOpen] = useState(false);
  const libraryMenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let active = true;
    api
      .knowledgeLibraries()
      .then((data) => {
        if (active) setLibraries(data);
      })
      .catch(() => {
        if (active) setLibraries([]);
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (libraryMenuRef.current && !libraryMenuRef.current.contains(event.target as Node)) {
        setLibraryMenuOpen(false);
      }
    }
    if (libraryMenuOpen) {
      document.addEventListener("mousedown", handleClickOutside);
      return () => document.removeEventListener("mousedown", handleClickOutside);
    }
  }, [libraryMenuOpen]);

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

  const { take } = attachments;
  const sendText = useCallback(
    (text: string) => {
      stickToBottom.current = true;
      void send(text, "text", { attachments: take() });
    },
    [send, take],
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

        {/* Knowledge Library Scope Selector */}
        <div ref={libraryMenuRef} className="relative">
          <button
            type="button"
            onClick={() => setLibraryMenuOpen((prev) => !prev)}
            data-testid="library-selector-button"
            className={cn(
              "flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium transition-colors",
              libraryId
                ? "border-accent/40 bg-accent/10 text-accent hover:bg-accent/15"
                : "border-line bg-surface text-ink-muted hover:border-line-strong hover:text-ink",
            )}
            title={libraryName ? f(m.chat.scopedToLibrary, { name: libraryName }) : m.chat.selectLibrary}
          >
            <BookOpen size={13} className={libraryId ? "text-accent" : "text-ink-faint"} />
            <span className="max-w-[110px] truncate sm:max-w-[160px]">
              {libraryName || m.chat.selectLibrary}
            </span>
            {libraryId ? (
              <span
                role="button"
                tabIndex={0}
                aria-label={m.chat.clearLibrary}
                onClick={(e) => {
                  e.stopPropagation();
                  void clearLibrary();
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.stopPropagation();
                    void clearLibrary();
                  }
                }}
                className="ml-0.5 rounded-full p-0.5 hover:bg-accent/20"
                data-testid="clear-library-button"
              >
                <X size={11} />
              </span>
            ) : (
              <ChevronDown size={12} className="opacity-60" />
            )}
          </button>

          {libraryMenuOpen ? (
            <div
              className="absolute right-0 top-full z-30 mt-1 w-64 rounded-xl border border-line bg-surface p-1 shadow-float"
              data-testid="library-selector-menu"
            >
              <div className="px-2 py-1.5 text-[11px] font-medium uppercase tracking-wider text-ink-faint">
                {m.chat.selectLibrary}
              </div>
              <button
                type="button"
                onClick={() => {
                  void clearLibrary();
                  setLibraryMenuOpen(false);
                }}
                data-testid="library-option-global"
                className={cn(
                  "flex w-full items-center justify-between rounded-lg px-2.5 py-1.5 text-left text-xs transition-colors",
                  !libraryId
                    ? "bg-surface-2 font-medium text-ink"
                    : "text-ink-muted hover:bg-surface-2 hover:text-ink",
                )}
              >
                <span>{m.chat.allLibraries}</span>
                {!libraryId ? <span className="text-accent text-[11px]">✓</span> : null}
              </button>

              {libraries.map((lib) => (
                <button
                  key={lib.id}
                  type="button"
                  onClick={() => {
                    void selectLibrary(lib.id, lib.name);
                    setLibraryMenuOpen(false);
                  }}
                  data-testid={`library-option-${lib.id}`}
                  className={cn(
                    "flex w-full items-center justify-between rounded-lg px-2.5 py-1.5 text-left text-xs transition-colors",
                    libraryId === lib.id
                      ? "bg-accent/10 font-medium text-accent"
                      : "text-ink-muted hover:bg-surface-2 hover:text-ink",
                  )}
                >
                  <span className="truncate">{lib.name}</span>
                  {libraryId === lib.id ? <span className="text-accent text-[11px]">✓</span> : null}
                </button>
              ))}
            </div>
          ) : null}
        </div>

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
              data-testid={mode === "voice" ? undefined : `mode-${key}`}
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

      {/* Active Library Scope Indicator Banner */}
      {libraryId && libraryName ? (
        <div
          data-testid="active-library-banner"
          className="mx-3 mb-1 flex items-center justify-between rounded-lg border border-accent/30 bg-accent/5 px-3 py-1 text-xs text-accent sm:mx-auto sm:w-full sm:max-w-3xl"
        >
          <div className="flex items-center gap-1.5 truncate">
            <BookOpen size={13} className="shrink-0" />
            <span className="truncate">{f(m.chat.scopedToLibrary, { name: libraryName })}</span>
          </div>
          <button
            type="button"
            onClick={() => void clearLibrary()}
            className="ml-2 shrink-0 text-xs font-medium text-ink-muted hover:text-ink underline"
          >
            {m.chat.clearLibrary}
          </button>
        </div>
      ) : null}

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
          <VoiceStage session={session} onExit={() => setMode("text")} offline={status?.offline_mode} />
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
            blocked={attachments.uploading ? m.knowledge.waitUploads : undefined}
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
