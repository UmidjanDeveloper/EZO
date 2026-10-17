"use client";

import { Button } from "@ezo/ui";
import { ArrowUp, AudioLines, Paperclip, Square } from "lucide-react";
import { useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { useI18n } from "@/lib/i18n/context";

interface ComposerProps {
  streaming: boolean;
  onSend: (text: string) => void;
  onStop: () => void;
  /** Switch to voice conversation (hidden when not provided). */
  onVoice?: () => void;
  /** Add files to EZO's knowledge (hidden when not provided). */
  onAttach?: (files: File[]) => void;
  /** Shown above the input, e.g. attached files and their status. */
  above?: ReactNode;
  autoFocus?: boolean;
}

const MAX_HEIGHT = 220;

export function Composer({ streaming, onSend, onStop, onVoice, onAttach, above, autoFocus }: ComposerProps) {
  const { m } = useI18n();
  const [text, setText] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    element.style.height = "auto";
    element.style.height = `${Math.min(element.scrollHeight, MAX_HEIGHT)}px`;
  }, [text]);

  function submit() {
    const value = text.trim();
    if (!value || streaming) return;
    onSend(value);
    setText("");
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      submit();
    }
  }

  return (
    <div className="mx-auto w-full max-w-3xl px-3 pb-3 sm:px-4 sm:pb-4">
      {above}
      <div className="flex items-end gap-2 rounded-2xl border border-line bg-surface p-2 shadow-card focus-within:border-accent/60">
        {onAttach ? (
          <>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => fileRef.current?.click()}
              aria-label={m.knowledge.attach}
              title={m.knowledge.attach}
              data-testid="composer-attach"
            >
              <Paperclip size={18} />
            </Button>
            <input
              ref={fileRef}
              type="file"
              multiple
              className="sr-only"
              tabIndex={-1}
              aria-hidden
              data-testid="composer-file-input"
              onChange={(event) => {
                const files = Array.from(event.target.files ?? []);
                event.target.value = "";
                if (files.length) onAttach(files);
              }}
            />
          </>
        ) : null}
        <label htmlFor="composer" className="sr-only">
          {m.chat.placeholder}
        </label>
        <textarea
          id="composer"
          ref={ref}
          value={text}
          rows={1}
          autoFocus={autoFocus}
          onChange={(event) => setText(event.target.value)}
          onKeyDown={onKeyDown}
          placeholder={m.chat.placeholder}
          className="max-h-[220px] min-h-10 flex-1 resize-none bg-transparent px-2 py-2 text-[15px] leading-6 text-ink placeholder:text-ink-faint focus:outline-none"
          data-testid="composer-input"
        />
        {onVoice && !text.trim() && !streaming ? (
          <Button
            variant="ghost"
            size="icon"
            onClick={onVoice}
            aria-label={m.voice.modeVoice}
            title={m.voice.modeVoice}
            data-testid="composer-voice"
          >
            <AudioLines size={18} />
          </Button>
        ) : null}
        {streaming ? (
          <Button variant="secondary" size="icon" onClick={onStop} aria-label={m.chat.stop} title={m.chat.stop}>
            <Square size={14} className="fill-current" />
          </Button>
        ) : (
          <Button
            variant="primary"
            size="icon"
            onClick={submit}
            disabled={!text.trim()}
            aria-label={m.chat.send}
            title={m.chat.send}
            data-testid="composer-send"
          >
            <ArrowUp size={18} />
          </Button>
        )}
      </div>
      <p className="mt-1.5 hidden px-2 text-xs text-ink-faint sm:block">{m.chat.hint}</p>
    </div>
  );
}
