"use client";

import { Button } from "@ezo/ui";
import { ArrowUp, Square } from "lucide-react";
import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { useI18n } from "@/lib/i18n/context";

interface ComposerProps {
  streaming: boolean;
  onSend: (text: string) => void;
  onStop: () => void;
  autoFocus?: boolean;
}

const MAX_HEIGHT = 220;

export function Composer({ streaming, onSend, onStop, autoFocus }: ComposerProps) {
  const { m } = useI18n();
  const [text, setText] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);

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
      <div className="flex items-end gap-2 rounded-2xl border border-line bg-surface p-2 shadow-card focus-within:border-accent/60">
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
