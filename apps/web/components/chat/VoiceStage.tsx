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
  storedVoiceVolume,
} from "@/lib/voice/engine";
import { voicePresence, type VoicePhase } from "@/lib/ezo-state";
import { createStoredValue } from "@/lib/stored-value";
import type { EzoAvatar } from "@ezo/avatar";
import { EzoHumanoid } from "../robot/EzoHumanoid";
import { CameraAttentionRow, useCameraAttention } from "./CameraAttention";
import type { useChatSession } from "./useChatSession";

type Session = ReturnType<typeof useChatSession>;


type VoiceLanguage = "auto" | LanguageCode;
const LANGUAGES: VoiceLanguage[] = ["auto", "uz", "en", "ru"];
const storedVoiceLanguage = createStoredValue<VoiceLanguage | "">(
  "ezo-voice-language",
  "",
  (value): value is VoiceLanguage | "" => value === "" || value === "auto" || value === "uz" || value === "en" || value === "ru",
);

/**
 * Hands-free conversation with EZO: tap the robot, speak, hear the answer.
 * After EZO finishes speaking it listens again, like talking to a person.
 */
export function VoiceStage({ session }: { session: Session }) {
  const { m, f, language: uiLanguage } = useI18n();
  const storedLanguage = storedVoiceLanguage.useValue();
  const volume = storedVoiceVolume.useValue();
  // "auto": EZO hears uz, en or ru and answers in the language it heard.
  const choice: VoiceLanguage = storedLanguage || "auto";
  const lastHeardRef = useRef<LanguageCode | null>(null);

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
  const [avatar, setAvatar] = useState<EzoAvatar | null>(null);
  const ackRef = useRef(false); // an acknowledgement clip is playing (not a conversation turn)
  const listenAfterAckRef = useRef<() => void>(() => undefined);
  const camera = useCameraAttention(avatar, {
    language: uiLanguage,
    providerKey: (voiceStatus?.text_to_speech ?? []).join(","),
    interaction: phase === "listening" || phase === "recognizing" ? "listening" : phase === "speaking" ? "speaking" : null,
    onPlayback: (event) => {
      if (event === "start") {
        ackRef.current = true;
        stopVoice();
        setNotice(null);
        setPhase("speaking");
      } else if (event === "unavailable" || event === "error") {
        // Not spoken: no provider, or the provider failed. Never a pretended playback.
        setNotice(m.voice.clap.unavailable);
      } else if (ackRef.current) {
        ackRef.current = false;
        setPhase("idle");
        listenAfterAckRef.current();
      }
    },
  });
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
    // The server recogniser can take any of the three languages; the browser's needs one.
    const listenLanguage = choice !== "auto" ? choice : useServer ? null : (lastHeardRef.current ?? uiLanguage);
    stopListeningRef.current = listenFn(listenLanguage, {
      onInterim: (text) => turn === turnRef.current && setHeard(text),
      onRecognizing: () => turn === turnRef.current && setPhase("recognizing"),
      onFinal: (text, info) => {
        if (turn !== turnRef.current) return;
        gotText = true;
        setHeard(text);
        const heardLanguage = info?.language ?? (choice !== "auto" ? choice : listenLanguage);
        void respond(text, turn, info?.speechSeconds ?? null, heardLanguage ?? null);
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

    async function respond(text: string, currentTurn: number, speechSeconds: number | null, heardLanguage: LanguageCode | null) {
      setPhase("thinking");
      const reply = await send(text, "voice", { speechSeconds, languageHint: heardLanguage });
      if (!mountedRef.current || currentTurn !== turnRef.current) return;
      if (!reply || !reply.content) {
        setPhase("idle");
        return;
      }
      const replyLanguage = reply.language ?? heardLanguage ?? uiLanguage;
      lastHeardRef.current = replyLanguage;
      const serverSpeech = (voiceStatus?.text_to_speech.length ?? 0) > 0;
      if (!serverSpeech && !hasVoiceFor(replyLanguage)) {
        setNotice(f(m.voice.noVoice, { language: m.voice.languages[replyLanguage] }));
      }
      setPhase("speaking");
      await speakReply(toSpeakableText(reply.content), replyLanguage, voiceStatus);
      if (!mountedRef.current || currentTurn !== turnRef.current) return;
      listenRef.current(); // keep the conversation going
    }
  }, [choice, errorNotice, f, m.voice, send, uiLanguage, voiceStatus]);

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
    // Only when the owner switched it on: after the spoken acknowledgement EZO starts listening.
    listenAfterAckRef.current = () => {
      if (camera.clap.startsListening && supported) listen();
    };
  }, [camera.clap.startsListening, listen, supported]);

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
      : phase === "recognizing"
        ? m.voice.recognizing
      : phase === "thinking"
        ? visible === "thinking"
          ? m.voice.thinking
          : m.presence[visible]
        : phase === "speaking"
          ? m.voice.speaking
          : m.voice.idle;

  return (
    <div
      className="ezo-night relative flex h-full flex-col items-center px-4 pb-6 pt-2"
      data-testid="voice-stage"
      data-engine={engine ?? "none"}
    >
      <EzoHumanoid state={visible} framing="bust" label={status} frame followPointer onPointerGaze={camera.pointer} onAvatar={setAvatar} className="absolute inset-0" />
      <div className="relative z-10 flex w-full max-w-2xl items-center justify-between gap-2">
        <input
          type="range"
          min={0}
          max={1}
          step={0.05}
          value={volume}
          aria-label={m.voice.volume}
          title={m.voice.volume}
          onChange={(event) => storedVoiceVolume.set(event.target.value)}
          className="h-1 w-24 cursor-pointer accent-sky-300"
          data-testid="voice-volume"
        />
      <div className="flex justify-end gap-1" role="group" aria-label={m.voice.language}>
        {LANGUAGES.map((code) => (
          <button
            key={code}
            type="button"
            onClick={() => storedVoiceLanguage.set(code)}
            aria-pressed={choice === code}
            title={code === "auto" ? m.voice.autoHint : m.voice.languages[code]}
            className={cn(
              "rounded-full px-2.5 py-1 text-xs font-medium uppercase tracking-wider transition-colors",
              choice === code ? "bg-sky-400/20 text-sky-200" : "text-slate-400 hover:text-slate-100",
            )}
          >
            {code === "auto" ? m.voice.auto : code}
          </button>
        ))}
      </div>
      </div>

      {/* The whole stage is the talk button: tap EZO to talk, interrupt or stop. */}
      <button
        type="button"
        onClick={toggle}
        className="relative z-10 min-h-0 w-full flex-1 rounded-3xl focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-sky-300"
        aria-label={status}
      />

      <div className="relative z-10 flex w-full flex-col items-center gap-3">
        <p className="text-sm font-medium tracking-wide text-sky-100/80" aria-live="polite" data-testid="voice-status">
          {status}
        </p>

        <AnimatePresence mode="wait">
          {heard ? (
            <motion.p
              key={heard}
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              className="max-w-xl text-center text-base text-slate-300"
              data-testid="voice-heard"
            >
              “{heard}”
            </motion.p>
          ) : null}
        </AnimatePresence>

        {caption && phase !== "listening" ? (
          <div
            className="max-h-[18vh] w-full max-w-2xl overflow-y-auto text-center text-lg leading-relaxed text-slate-50 [text-shadow:0_1px_8px_rgba(0,0,0,0.8)]"
            data-testid="voice-caption"
          >
            {toSpeakableText(caption)}
          </div>
        ) : null}

        {notice ? <p className="max-w-md text-center text-sm text-amber-300" role="status">{notice}</p> : null}
        <CameraAttentionRow camera={camera} />
      </div>

      <button
        type="button"
        onClick={toggle}
        disabled={!supported}
        data-testid="voice-toggle"
        aria-label={phase === "idle" ? m.voice.start : m.voice.stop}
        className={cn(
          "relative z-10 flex h-16 w-16 items-center justify-center rounded-full transition-all disabled:opacity-40",
          phase === "idle"
            ? "bg-accent text-on-accent shadow-[0_0_30px_-4px_var(--accent)] hover:scale-105"
            : "border border-slate-500 bg-slate-900/70 text-slate-100 hover:border-red-400 hover:text-red-300",
        )}
      >
        {phase === "idle" ? <Mic size={26} /> : <Square size={20} className="fill-current" />}
      </button>
      <p className="relative z-10 mt-2 text-xs text-slate-400">{supported ? m.voice.hint : m.voice.unsupportedHint}</p>
    </div>
  );
}
