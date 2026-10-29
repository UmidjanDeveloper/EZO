"use client";

import type { LanguageCode } from "@ezo/shared";
import { cn } from "@ezo/ui";
import { AnimatePresence, motion } from "framer-motion";
import { Languages, Mic, Square, X, Settings2 } from "lucide-react";
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
import { acknowledgementLanguage } from "@/lib/perception";
import { otherSide, parseInterpreterCommand, speakerSide, type LanguagePair } from "@/lib/voice/interpreter";
import { voicePresence, type VoicePhase } from "@/lib/ezo-state";
import { createStoredValue } from "@/lib/stored-value";
import type { EzoAvatar } from "@ezo/avatar";
import { EzoHumanoid } from "../robot/EzoHumanoid";
import { ClapRow, useClap } from "./ClapControls";
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
export function VoiceStage({ session, onExit, offline = false }: { session: Session; onExit: () => void; offline?: boolean }) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = dialogRef.current;
    dialog?.showModal();
    return () => dialog?.close();
  }, []);
  const { m, f, language: uiLanguage } = useI18n();
  const storedLanguage = storedVoiceLanguage.useValue();
  const volume = storedVoiceVolume.useValue();
  // "auto": EZO hears uz, en or ru and answers in the language it heard.
  const choice: VoiceLanguage = storedLanguage || "auto";
  const lastHeardRef = useRef<LanguageCode | null>(null);
  const [lastHeardLanguage, setLastHeardLanguage] = useState<LanguageCode | null>(null);

  const [phase, setPhase] = useState<VoicePhase>("idle");
  const [heard, setHeard] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  // Interpreter mode: two people take turns; each turn is translated and spoken in the other language.
  const [interp, setInterp] = useState<{ pair: LanguagePair; next: LanguageCode } | null>(null);
  const interpRef = useRef(interp);
  const [interpLine, setInterpLine] = useState<{ original: string; translated: string } | null>(null);
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
  const clap = useClap(avatar, {
    language: acknowledgementLanguage(choice, lastHeardLanguage, uiLanguage),
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

  /** Start (pair) or stop (null) interpreter mode, say so aloud, then keep listening. */
  const switchInterpreter = useCallback(
    async (pair: LanguagePair | null, currentTurn: number) => {
      const next = pair ? { pair, next: pair[0] } : null;
      interpRef.current = next;
      setInterp(next);
      setInterpLine(null);
      setNotice(null);
      const line = pair
        ? f(m.voice.interpreter.started, { a: m.voice.languages[pair[0]], b: m.voice.languages[pair[1]] })
        : m.voice.interpreter.stopped;
      setHeard("");
      setPhase("speaking");
      await speakReply(line, uiLanguage, voiceStatus);
      if (!mountedRef.current || currentTurn !== turnRef.current) return;
      if (pair) listenRef.current();
      else setPhase("idle");
    },
    [f, m.voice, uiLanguage, voiceStatus],
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
    // Interpreting, the browser listens for the side whose turn it is.
    const interpreting = interpRef.current;
    const listenLanguage = interpreting
      ? useServer
        ? null
        : interpreting.next
      : choice !== "auto"
        ? choice
        : useServer
          ? null
          : (lastHeardRef.current ?? uiLanguage);
    stopListeningRef.current = listenFn(listenLanguage, {
      onInterim: (text) => turn === turnRef.current && setHeard(text),
      onRecognizing: () => turn === turnRef.current && setPhase("recognizing"),
      onFinal: (text, info) => {
        if (turn !== turnRef.current) return;
        gotText = true;
        setHeard(text);
        const heardLanguage = info?.language ?? (interpreting || choice === "auto" ? listenLanguage : choice);
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
      const command = parseInterpreterCommand(text, heardLanguage);
      const active = interpRef.current;
      if (command?.kind === "start" || (command?.kind === "stop" && active)) {
        await switchInterpreter(command.kind === "start" ? command.pair : null, currentTurn);
        return;
      }
      if (active) {
        await interpretTurn(text, heardLanguage, active, currentTurn);
        return;
      }
      setPhase("thinking");
      const reply = await send(text, "voice", { speechSeconds, languageHint: heardLanguage });
      if (!mountedRef.current || currentTurn !== turnRef.current) return;
      if (!reply || !reply.content) {
        setPhase("idle");
        return;
      }
      const replyLanguage = reply.language ?? heardLanguage ?? uiLanguage;
      lastHeardRef.current = replyLanguage;
      setLastHeardLanguage(replyLanguage);
      const serverSpeech = (voiceStatus?.text_to_speech.length ?? 0) > 0;
      if (!serverSpeech && !hasVoiceFor(replyLanguage)) {
        setNotice(f(m.voice.noVoice, { language: m.voice.languages[replyLanguage] }));
      }
      setPhase("speaking");
      await speakReply(toSpeakableText(reply.content), replyLanguage, voiceStatus);
      if (!mountedRef.current || currentTurn !== turnRef.current) return;
      listenRef.current(); // keep the conversation going
    }

    /** One interpreted turn: what was said is translated and spoken in the other language. */
    async function interpretTurn(text: string, heardLanguage: LanguageCode | null, active: { pair: LanguagePair; next: LanguageCode }, currentTurn: number) {
      const from = speakerSide(active.pair, heardLanguage, active.next);
      const into = otherSide(active.pair, from);
      setPhase("thinking");
      try {
        const result = await api.translate({ text, source: from, target: into });
        if (!mountedRef.current || currentTurn !== turnRef.current) return;
        setInterpLine({ original: text, translated: result.text });
        const next = { pair: active.pair, next: into }; // the other person answers next
        interpRef.current = next;
        setInterp(next);
        setPhase("speaking");
        await speakReply(result.text, into, voiceStatus);
      } catch (error) {
        if (!mountedRef.current || currentTurn !== turnRef.current) return;
        setNotice(f(m.voice.interpreter.failed, { detail: error instanceof Error ? error.message : String(error) }));
      }
      if (!mountedRef.current || currentTurn !== turnRef.current) return;
      listenRef.current();
    }
  }, [choice, errorNotice, f, m.voice, send, switchInterpreter, uiLanguage, voiceStatus]);

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
      if (clap.startsListening && supported) listen();
    };
  }, [clap.startsListening, listen, supported]);

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
    <dialog ref={dialogRef} onCancel={(event) => { event.preventDefault(); onExit(); }} aria-label={m.voice.modeVoice} className="fixed inset-0 m-0 h-dvh max-h-none w-screen max-w-none border-0 bg-[#030814] p-0 text-slate-100 backdrop:bg-black">
    <div
      className="ezo-night relative isolate h-dvh w-full overflow-hidden"
      data-testid="voice-stage"
      data-engine={engine ?? "none"}
    >

      <div className="pointer-events-none absolute inset-x-0 top-0 z-30 flex items-start justify-between gap-3 bg-gradient-to-b from-[#030814]/80 to-transparent p-4 pt-[max(1rem,env(safe-area-inset-top))]">
        <div className="text-[11px] tracking-wide text-sky-100/70" aria-live="polite">
          <span className="text-sm font-semibold tracking-[0.35em] text-sky-100">EZO</span>
          {offline ? <p className="mt-2 text-amber-300" data-testid="voice-offline">{m.chat.offlineTitle}</p> : null}
          <p className="mt-2" data-testid="voice-sensor-status">{clap.text}</p>
          {interp ? (
            <div className="pointer-events-auto mt-3 flex flex-wrap items-center gap-2" data-testid="voice-interpreter">
              <span className="flex items-center gap-1.5 rounded-full border border-amber-300/40 bg-amber-400/10 px-3 py-1 text-xs font-semibold text-amber-200">
                <Languages size={14} />
                {f(m.voice.interpreter.badge, { a: interp.pair[0].toUpperCase(), b: interp.pair[1].toUpperCase() })}
              </span>
              <span className="text-[11px] text-sky-100/70">{m.voice.interpreter.next}:</span>
              {interp.pair.map((code) => (
                <button
                  key={code}
                  type="button"
                  aria-pressed={interp.next === code}
                  onClick={() => {
                    const next = { pair: interp.pair, next: code };
                    interpRef.current = next;
                    setInterp(next);
                  }}
                  className={cn("rounded-full px-2.5 py-1 text-xs font-medium uppercase", interp.next === code ? "bg-sky-400/25 text-sky-100" : "text-slate-400 hover:text-slate-100")}
                >
                  {code}
                </button>
              ))}
              <button
                type="button"
                data-testid="voice-interpreter-stop"
                onClick={() => void switchInterpreter(null, ++turnRef.current)}
                className="rounded-full border border-slate-500 px-2.5 py-1 text-xs text-slate-200 hover:border-red-400 hover:text-red-300"
              >
                {m.voice.interpreter.stop}
              </button>
            </div>
          ) : null}
        </div>
        <button type="button" data-testid="mode-text" onClick={onExit} aria-label={m.voice.modeText} className="pointer-events-auto flex h-11 w-11 shrink-0 items-center justify-center rounded-full border border-sky-100/20 bg-slate-950/60 hover:bg-slate-800"><X size={20} /></button>
      </div>
      <details className="absolute right-4 top-20 z-40 max-h-[65dvh] w-auto open:w-[min(24rem,calc(100%-2rem))] overflow-y-auto rounded-2xl border border-sky-100/10 bg-slate-950/80 p-2 backdrop-blur-xl" data-testid="voice-settings">
        <summary className="flex min-h-7 min-w-7 cursor-pointer items-center justify-end gap-2 text-xs text-sky-100"><Settings2 size={18} /><span className="sr-only">{m.voice.volume} / {m.voice.language}</span></summary>
      <div className="flex w-full items-center justify-between gap-2 py-4">
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

      <button
        type="button"
        data-testid="voice-interpreter-start"
        disabled={!supported}
        onClick={() => {
          (document.activeElement as HTMLElement | null)?.closest("details")?.removeAttribute("open");
          void switchInterpreter(["uz", "en"], ++turnRef.current);
        }}
        className="mb-2 flex w-full items-center gap-2 rounded-xl border border-sky-100/10 px-3 py-2 text-left text-xs text-sky-100 hover:bg-sky-400/10 disabled:opacity-40"
      >
        <Languages size={16} />
        <span>
          <span className="block font-semibold">{m.voice.interpreter.start}</span>
          <span className="block text-sky-100/60">{m.voice.interpreter.hint}</span>
        </span>
      </button>
      <ClapRow clap={clap} />
      </details>
      <div className="absolute inset-0" data-testid="voice-scene"
        onPointerMove={(event) => { const r = event.currentTarget.getBoundingClientRect(); avatar?.setGaze({ yaw: (event.clientX-r.left)/r.width*2-1, pitch: (1-(event.clientY-r.top)/r.height*2)*0.6 }); }}
        onPointerLeave={() => avatar?.setGaze(null)}>
        <EzoHumanoid state={visible} framing="bust" style="holographic" label={status} onAvatar={setAvatar} className="absolute inset-0" />
        <button type="button" onClick={toggle} className="absolute inset-0 z-10 focus-visible:outline-2 focus-visible:outline-sky-300" aria-label={status} />
      </div>
      <div className="pointer-events-none absolute inset-x-0 bottom-24 z-10 flex max-h-[30dvh] flex-col items-center gap-2 overflow-y-auto bg-gradient-to-t from-[#030814]/80 to-transparent px-6 py-3 text-center" data-testid="voice-controls">
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

        {interp && interpLine ? (
          <div className="pointer-events-auto w-full max-w-2xl text-center" data-testid="voice-interpretation">
            <p className="text-sm text-slate-400">{interpLine.original}</p>
            <p className="text-lg leading-relaxed text-amber-100 [text-shadow:0_1px_8px_rgba(0,0,0,0.8)]">{interpLine.translated}</p>
          </div>
        ) : !interp && caption && phase !== "listening" ? (
          <div
            className="pointer-events-auto max-h-[12dvh] w-full max-w-2xl overflow-y-auto text-center text-lg leading-relaxed text-slate-50 [text-shadow:0_1px_8px_rgba(0,0,0,0.8)]"
            data-testid="voice-caption"
          >
            {toSpeakableText(caption)}
          </div>
        ) : null}

        {notice ? <p className="max-w-md text-center text-sm text-amber-300" role="status">{notice}</p> : null}
      </div>

      <button
        type="button"
        onClick={toggle}
        disabled={!supported}
        data-testid="voice-toggle"
        aria-label={phase === "idle" ? m.voice.start : m.voice.stop}
        className={cn(
          "absolute bottom-[max(1.5rem,env(safe-area-inset-bottom))] left-1/2 z-20 flex h-14 w-14 -translate-x-1/2 items-center justify-center rounded-full transition-all disabled:opacity-40",
          phase === "idle"
            ? "bg-accent text-on-accent shadow-[0_0_30px_-4px_var(--accent)] hover:scale-105"
            : "border border-slate-500 bg-slate-900/70 text-slate-100 hover:border-red-400 hover:text-red-300",
        )}
      >
        {phase === "idle" ? <Mic size={26} /> : <Square size={20} className="fill-current" />}
      </button>

    </div>
    </dialog>
  );
}
