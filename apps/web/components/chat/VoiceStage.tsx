"use client";

import type { LanguageCode } from "@ezo/shared";
import { cn } from "@ezo/ui";
import { AnimatePresence, motion } from "framer-motion";
import { Mic, Square } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n/context";
import { hasVoiceFor, speechRecognitionSupported, toSpeakableText } from "@/lib/speech";
import { useApiData } from "@/lib/use-api-data";
import {
  listenWithBrowser,
  listenWithServer,
  pickListener,
  SERVER_FAILED,
  serverRecordingSupported,
  speakReply,
  stopVoice,
} from "@/lib/voice/engine";
import { voicePresence, type VoicePhase } from "@/lib/ezo-state";
import { createStoredValue } from "@/lib/stored-value";
import { EzoPresence } from "../robot/EzoPresence";
import type { useChatSession } from "./useChatSession";

type Session = ReturnType<typeof useChatSession>;


const LANGUAGES: LanguageCode[] = ["uz", "en", "ru"];
const storedVoiceLanguage = createStoredValue<LanguageCode | "">(
  "ezo-voice-language",
  "",
  (value): value is LanguageCode | "" => value === "" || value === "uz" || value === "en" || value === "ru",
);

/**
 * Hands-free conversation with EZO: tap the robot, speak, hear the answer.
 * After EZO finishes speaking it listens again, like talking to a person.
 */
export function VoiceStage({ session }: { session: Session }) {
  const { m, f, language: uiLanguage } = useI18n();
  const storedLanguage = storedVoiceLanguage.useValue();
  const language: LanguageCode = storedLanguage || uiLanguage;

  const [phase, setPhase] = useState<VoicePhase>("idle");
  const [heard, setHeard] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  // Server voice (VoiceStudio, OpenAI…) when the API has a provider; the browser otherwise.
  const fetchVoiceStatus = useCallback(() => api.voiceStatus(), []);
  const { data: voiceStatus } = useApiData(fetchVoiceStatus);
  const [serverFailed, setServerFailed] = useState(false);
  const serverFailedRef = useRef(false);
  const [canRecord] = useState(() => serverRecordingSupported() || speechRecognitionSupported());
  const engine = canRecord ? pickListener(voiceStatus, serverFailed) : null;
  const supported = engine !== null;

  const stopListeningRef = useRef<(() => void) | null>(null);
  const turnRef = useRef(0); // increments on every user action; stale callbacks check it
  const mountedRef = useRef(true);
  const listenRef = useRef<() => void>(() => undefined);

  const { send, stop: stopStreaming, messages } = session;
  const visible = voicePresence(phase, session.presence);
  const lastAssistant = [...messages].reverse().find((message) => message.role === "assistant");
  const caption = lastAssistant?.error ? lastAssistant.error.message : lastAssistant?.content ?? "";

  const errorNotice = useCallback(
    (error: string) => {
      if (error === "not-allowed" || error === "service-not-allowed") return m.voice.micDenied;
      if (error === "no-speech" || error === "aborted") return m.voice.noSpeech;
      if (error === "network") return m.voice.network;
      return m.voice.failed;
    },
    [m.voice],
  );

  const listen = useCallback(() => {
    const turn = ++turnRef.current;
    stopVoice();
    setHeard("");
    setPhase("listening");
    let gotText = false;

    const useServer = pickListener(voiceStatus, serverFailedRef.current) === "server";
    if (!useServer) setNotice((current) => (serverFailedRef.current ? current : null));
    else setNotice(null);
    const listenFn = useServer ? listenWithServer : listenWithBrowser;
    stopListeningRef.current = listenFn(language, {
      onInterim: (text) => turn === turnRef.current && setHeard(text),
      onFinal: (text, info) => {
        if (turn !== turnRef.current) return;
        gotText = true;
        setHeard(text);
        void respond(text, turn, info?.speechSeconds ?? null);
      },
      onEnd: (error) => {
        stopListeningRef.current = null;
        if (turn !== turnRef.current || gotText) return;
        if (error === SERVER_FAILED) {
          // The server voice is down: say so once and continue with the browser's speech.
          serverFailedRef.current = true;
          setServerFailed(true);
          setNotice(m.voice.serverFallback);
          if (speechRecognitionSupported()) {
            listenRef.current();
            return;
          }
        }
        setPhase("idle");
        if (error && error !== SERVER_FAILED) setNotice(errorNotice(error));
      },
    });

    async function respond(text: string, currentTurn: number, speechSeconds: number | null) {
      setPhase("thinking");
      const reply = await send(text, "voice", { speechSeconds });
      if (!mountedRef.current || currentTurn !== turnRef.current) return;
      if (!reply || !reply.content) {
        setPhase("idle");
        return;
      }
      const replyLanguage = reply.language ?? language;
      const serverSpeech = (voiceStatus?.text_to_speech.length ?? 0) > 0;
      if (!serverSpeech && !hasVoiceFor(replyLanguage)) {
        setNotice(f(m.voice.noVoice, { language: m.voice.languages[replyLanguage] }));
      }
      setPhase("speaking");
      await speakReply(toSpeakableText(reply.content), replyLanguage, voiceStatus);
      if (!mountedRef.current || currentTurn !== turnRef.current) return;
      listenRef.current(); // keep the conversation going
    }
  }, [errorNotice, f, language, m.voice, send, voiceStatus]);

  useEffect(() => {
    listenRef.current = listen;
  }, [listen]);

  /** One button for everything: start, stop listening, stop thinking, interrupt speaking. */
  const toggle = useCallback(() => {
    if (!supported) return;
    if (phase === "idle") {
      listen();
    } else if (phase === "speaking") {
      listen(); // interrupt EZO and talk
    } else {
      turnRef.current += 1;
      stopListeningRef.current?.();
      stopStreaming();
      stopVoice();
      setPhase("idle");
    }
  }, [listen, phase, stopStreaming, supported]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      turnRef.current += 1;
      stopListeningRef.current?.();
      stopVoice();
    };
  }, []);

  const status = !supported
    ? m.voice.unsupported
    : phase === "listening"
      ? m.voice.listening
      : phase === "thinking"
        ? visible === "thinking"
          ? m.voice.thinking
          : m.presence[visible]
        : phase === "speaking"
          ? m.voice.speaking
          : m.voice.idle;

  return (
    <div className="flex h-full flex-col items-center px-4 pb-6 pt-2" data-testid="voice-stage" data-engine={engine ?? "none"}>
      <div className="flex w-full max-w-2xl justify-end gap-1" role="group" aria-label={m.voice.language}>
        {LANGUAGES.map((code) => (
          <button
            key={code}
            type="button"
            onClick={() => storedVoiceLanguage.set(code)}
            aria-pressed={language === code}
            className={cn(
              "rounded-full px-2.5 py-1 text-xs font-medium uppercase tracking-wider transition-colors",
              language === code ? "bg-accent/15 text-accent" : "text-ink-faint hover:text-ink",
            )}
          >
            {code}
          </button>
        ))}
      </div>

      <div className="flex min-h-0 w-full flex-1 flex-col items-center justify-center gap-4">
        <button
          type="button"
          onClick={toggle}
          className="rounded-full focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-accent"
          aria-label={status}
        >
          <EzoPresence state={visible} size={290} className="max-h-[44vh] max-w-[72vw]" />
        </button>

        <p className="text-sm font-medium tracking-wide text-ink-muted" aria-live="polite" data-testid="voice-status">
          {status}
        </p>

        <AnimatePresence mode="wait">
          {heard ? (
            <motion.p
              key={heard}
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              className="max-w-xl text-center text-base text-ink-faint"
              data-testid="voice-heard"
            >
              “{heard}”
            </motion.p>
          ) : null}
        </AnimatePresence>

        {caption && phase !== "listening" ? (
          <div
            className="max-h-[22vh] w-full max-w-2xl overflow-y-auto text-center text-lg leading-relaxed text-ink"
            data-testid="voice-caption"
          >
            {toSpeakableText(caption)}
          </div>
        ) : null}

        {notice ? <p className="max-w-md text-center text-sm text-warning" role="status">{notice}</p> : null}
      </div>

      <button
        type="button"
        onClick={toggle}
        disabled={!supported}
        data-testid="voice-toggle"
        aria-label={phase === "idle" ? m.voice.start : m.voice.stop}
        className={cn(
          "flex h-16 w-16 items-center justify-center rounded-full transition-all disabled:opacity-40",
          phase === "idle"
            ? "bg-accent text-on-accent shadow-[0_0_30px_-4px_var(--accent)] hover:scale-105"
            : "border border-line-strong bg-surface text-ink hover:border-danger hover:text-danger",
        )}
      >
        {phase === "idle" ? <Mic size={26} /> : <Square size={20} className="fill-current" />}
      </button>
      <p className="mt-2 text-xs text-ink-faint">{supported ? m.voice.hint : m.voice.unsupportedHint}</p>
    </div>
  );
}
