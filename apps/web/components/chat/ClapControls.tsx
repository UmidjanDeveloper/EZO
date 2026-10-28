"use client";

import type { EzoAvatar } from "@ezo/avatar";
import { acknowledgement, ClapSession, VoiceReaction, type AcknowledgementSpeaker, type ClapDetected, type Diagnostics, type Language, type MicrophoneStatus } from "@ezo/perception-client";
import { cn } from "@ezo/ui";
import { useCallback, useEffect, useRef, useState } from "react";
import { useI18n } from "@/lib/i18n/context";
import { createAcknowledgementSpeaker, storedClapListening, storedClapStartsListening, type TtsInfo } from "@/lib/perception";

export interface AcknowledgementHooks {
  /** The acknowledgement clip started / ended / could not be produced. */
  onPlayback: (phase: "start" | "end" | "unavailable" | "error") => void;
  /** Spoken language selected for this conversation (UI language only as fallback). */
  language: Language;
  /** Changes when the server's voice provider changes (drops the clip cache). */
  providerKey: string;
  /** While EZO speaks, claps are ignored (its own voice must not trigger one). */
  interaction: "listening" | "speaking" | null;
}

/**
 * The clap acknowledgement on the voice stage: a separate microphone consent, off by
 * default, with its own Stop. A clap is detected on this device (nothing recorded or
 * uploaded) and answered with a short spoken phrase through the real server voice.
 */
export function useClap(avatar: EzoAvatar | null, hooks: AcknowledgementHooks) {
  const { m, f } = useI18n();
  const tc = m.voice.clap;
  const sessionRef = useRef<ClapSession | null>(null);
  const hooksRef = useRef(hooks);
  const [indicator, setIndicator] = useState<HTMLElement | null>(null);
  const register = useCallback((element: HTMLElement | null) => {
    if (element) setIndicator((previous) => (previous === element ? previous : element));
  }, []);
  const [microphone, setMicrophone] = useState<{ status: MicrophoneStatus; error?: string }>({ status: "off" });
  const [diagnostics, setDiagnostics] = useState<Diagnostics | null>(null);
  const [lastClap, setLastClap] = useState<{ at: number; evidence: ClapDetected["evidence"] } | null>(null);
  const [tts, setTts] = useState<TtsInfo | null>(null);
  const clapConsent = storedClapListening.useValue();
  const clapStartsListening = storedClapStartsListening.useValue();

  useEffect(() => {
    hooksRef.current = hooks;
    sessionRef.current?.setInteraction(hooks.interaction);
  }, [hooks]);

  // One clap session per mounted figure; released with it (stage closed, mode changed).
  useEffect(() => {
    if (!avatar || !indicator) return;
    const speaker: AcknowledgementSpeaker = createAcknowledgementSpeaker(() => hooksRef.current.providerKey, setTts);
    const reaction = new VoiceReaction(speaker, (event) => {
      if (event.type === "start") hooksRef.current.onPlayback("start");
      else if (event.type === "end") hooksRef.current.onPlayback("end");
      else if (event.type === "unavailable") hooksRef.current.onPlayback("unavailable");
      else if (event.type === "error") hooksRef.current.onPlayback("error");
    });
    const session = new ClapSession({
      microphoneIndicator: indicator,
      onMicrophone: (status, error) => setMicrophone({ status, error }),
      onDiagnostics: setDiagnostics,
      onClap: (event) => {
        // Acknowledgement only: a short spoken "I'm listening." Never a tool, a send or listening by itself.
        setLastClap({ at: event.timestampMs, evidence: event.evidence });
        try {
          void reaction.react(acknowledgement(event, hooksRef.current.language));
        } catch {
          // below the detector's confidence floor: ignored
        }
      },
    });
    sessionRef.current = session;
    session.setInteraction(hooksRef.current.interaction);
    const onVisibility = () => session.setVisible(!document.hidden);
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      reaction.stop();
      speaker.stop();
      session.stop();
      sessionRef.current = null;
      setMicrophone({ status: "off" });
    };
  }, [avatar, indicator]);

  const micRunning = microphone.status === "active" || microphone.status === "requesting";
  const toggle = () => {
    if (micRunning) {
      sessionRef.current?.stopClap();
      return;
    }
    storedClapListening.set("on");
    void sessionRef.current?.startClap();
  };
  const disable = () => {
    sessionRef.current?.stopClap();
    storedClapListening.set("off");
  };
  useEffect(() => {
    if (clapConsent === "off") sessionRef.current?.stopClap();
  }, [clapConsent]);

  const micWords: Record<MicrophoneStatus, string> = {
    off: tc.off,
    requesting: tc.requesting,
    active: tc.active,
    error: /denied|NotAllowed|permission/i.test(microphone.error ?? "") ? tc.denied : f(tc.error, { detail: microphone.error ?? "" }),
  };

  return {
    register,
    available: Boolean(avatar && indicator),
    consent: clapConsent === "on",
    running: micRunning,
    status: microphone.status,
    text: micWords[microphone.status],
    buttonText: micRunning ? tc.stop : tc.listen,
    privacy: tc.privacy,
    toggle,
    disable,
    startsListening: clapStartsListening === "on",
    setStartsListening: (on: boolean) => storedClapStartsListening.set(on ? "on" : "off"),
    last: lastClap,
    heardText: tc.heard,
    count: diagnostics?.clapCount ?? 0,
    diagnostics,
    tts,
    /** Plain-text Diagnostics for the owner: numbers and words only (no audio). */
    report: (): string => {
      const perf = avatar?.getPerformance() ?? null;
      const lines: [string, unknown][] = [
        ["EZO web diagnostics", ""],
        ["version", process.env.NEXT_PUBLIC_EZO_VERSION ?? "dev"],
        ["sha", process.env.NEXT_PUBLIC_EZO_BUILD_SHA ?? "dev"],
        ["at", new Date().toISOString()],
        ["language", hooksRef.current.language],
        ["voice.provider", hooksRef.current.providerKey || "—"],
        ["figure.renderer", avatar?.renderer ?? "—"],
        ["figure.points", avatar?.canvas.dataset.points ?? "—"],
        ["figure.power", avatar?.canvas.dataset.power ?? "—"],
        ["figure.frames", avatar?.getFrameCount() ?? 0],
        ["figure.frameMs", perf?.frameMs ?? 0],
        ["figure.drawMs", perf?.drawMs ?? 0],
        ["figure.fps", perf?.fps ?? 0],
        ["figure.heapMb", perf?.heapMb ?? "—"],
        ["figure.liveLevel", avatar?.hasLiveLevel() ?? false],
        ["microphone", microphone.status],
        ["clap.count", diagnostics?.clapCount ?? 0],
        ["tts.provider", tts?.provider ?? "—"],
        ["tts.latencyMs", tts?.latencyMs ?? "—"],
        ["tts.cached", tts?.cached ?? "—"],
        ["lastError", diagnostics?.lastError ?? "—"],
      ];
      return lines.map(([k, v]) => (k === "EZO web diagnostics" ? k : `${k}: ${String(v)}`)).join("\n");
    },
  };
}

export function ClapRow({ clap }: { clap: ReturnType<typeof useClap> }) {
  const { m } = useI18n();
  const dot = cn(
    "inline-block h-2 w-2 rounded-full",
    clap.status === "active"
      ? "bg-sky-400 shadow-[0_0_8px_rgba(56,189,248,0.9)]"
      : clap.status === "requesting"
        ? "bg-amber-400"
        : clap.status === "error"
          ? "bg-red-400"
          : "bg-slate-500",
  );
  return (
    <div
      className="relative z-10 flex w-full max-w-2xl flex-col items-center gap-1 text-xs text-slate-300"
      data-testid="clap-controls"
      data-clap-count={clap.count}
      data-tts-provider={clap.tts?.provider ?? ""}
    >
      <div className="flex flex-wrap items-center justify-center gap-3">
        <span className="flex items-center gap-1.5" role="status" data-testid="clap-state" data-microphone={clap.status}>
          <span className={dot} aria-hidden />
          {clap.text}
        </span>
        <button
          type="button"
          onClick={clap.toggle}
          disabled={!clap.available}
          className="rounded-full border border-slate-600 px-2.5 py-0.5 text-slate-100 transition-colors hover:border-sky-300 disabled:cursor-default disabled:opacity-50"
          data-testid="clap-toggle"
        >
          {clap.buttonText}
        </button>
        <label className="flex items-center gap-1 text-[11px] text-slate-400">
          <input type="checkbox" checked={clap.startsListening} onChange={(e) => clap.setStartsListening(e.target.checked)} data-testid="clap-starts-listening" />
          {m.voice.clap.startsListening}
        </label>
        <span ref={(el) => clap.register(el)} className="text-[10px] uppercase tracking-wide text-slate-500" data-testid="microphone-indicator" />
        {clap.last ? (
          <span className="text-amber-200" data-testid="clap-heard">
            {clap.heardText} ×{clap.count}
          </span>
        ) : null}
      </div>
      <p className="max-w-md text-center text-[11px] text-slate-500">{clap.privacy}</p>
      <DiagnosticsPanel report={clap.report} />
    </div>
  );
}

/** Hidden by default; the owner opens it, copies the plain-text report and pastes it back. */
function DiagnosticsPanel({ report }: { report: () => string }) {
  const { m } = useI18n();
  const [text, setText] = useState("");
  const [copied, setCopied] = useState(false);
  const refresh = () => {
    setText(report());
    setCopied(false);
  };
  const copy = async () => {
    const value = report();
    setText(value);
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
    } catch {
      setCopied(false); // the text stays visible for a manual copy
    }
  };
  return (
    <details className="w-full max-w-md text-[11px] text-slate-400" data-testid="diagnostics" onToggle={(e) => e.currentTarget.open && refresh()}>
      <summary className="cursor-pointer text-center text-slate-500">{m.voice.diagnostics.title}</summary>
      <p className="mt-1 text-center">{m.voice.diagnostics.note}</p>
      <div className="mt-1 flex justify-center gap-2">
        <button type="button" onClick={refresh} className="rounded-full border border-slate-600 px-2.5 py-0.5 text-slate-100" data-testid="diagnostics-refresh">
          ↻
        </button>
        <button type="button" onClick={() => void copy()} className="rounded-full border border-slate-600 px-2.5 py-0.5 text-slate-100" data-testid="diagnostics-copy">
          {copied ? m.voice.diagnostics.copied : m.voice.diagnostics.copy}
        </button>
      </div>
      <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap rounded bg-slate-900/60 p-2 text-left text-[10px] text-slate-300" data-testid="diagnostics-text">
        {text}
      </pre>
    </details>
  );
}
