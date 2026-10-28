"use client";

import { MotionAdapter, type AttentionView, type EzoAvatar, type Gaze, type VisionStatus } from "@ezo/avatar";
import type { MicrophoneStatus } from "@ezo/face-tracking";
import { acknowledgement, loadVisionAssets, PerceptionSession, VoiceReaction, type AcknowledgementSpeaker, type AssetsReadiness, type ClapDetected, type Diagnostics, type Language } from "@ezo/perception-client";
import { cn } from "@ezo/ui";
import { useCallback, useEffect, useRef, useState } from "react";
import { useI18n } from "@/lib/i18n/context";
import { createAcknowledgementSpeaker, storedClapListening, storedClapStartsListening, VISION_BASE, type TtsInfo } from "@/lib/perception";

const OFF: VisionStatus = { camera: "off", since: 0 };

export interface AcknowledgementHooks {
  /** The acknowledgement clip started / ended / could not be produced. */
  onPlayback: (phase: "start" | "end" | "unavailable" | "error") => void;
  /** Spoken language for the acknowledgement (the UI language). */
  language: Language;
  /** Changes when the server's voice provider changes (drops the clip cache). */
  providerKey: string;
  /** While EZO listens or speaks, the engine follows that mode and ignores claps while speaking. */
  interaction: "listening" | "speaking" | null;
}

/**
 * Camera attention and the clap acknowledgement on the voice stage, on the real perception
 * engine (@ezo/face-tracking in a worker, assets served from this origin and verified by
 * SHA256). The camera button is enabled only once the bundled assets validate; the clap
 * microphone is a separate consent, off by default, with its own Stop. Nothing is recorded,
 * uploaded or identified. A simulated (CI) camera is labelled as such by the engine status.
 */
export function useCameraAttention(avatar: EzoAvatar | null, hooks: AcknowledgementHooks) {
  const { m, f } = useI18n();
  const t = m.voice.camera;
  const tc = m.voice.clap;
  const adapterRef = useRef<MotionAdapter | null>(null);
  const sessionRef = useRef<PerceptionSession | null>(null);
  const speakerRef = useRef<AcknowledgementSpeaker | null>(null);
  const reactionRef = useRef<VoiceReaction | null>(null);
  const hooksRef = useRef(hooks);
  // The row registers its DOM nodes (hidden video, the engine's indicator spans) once mounted.
  const [nodes, setNodes] = useState<{ video?: HTMLVideoElement; camera?: HTMLElement; microphone?: HTMLElement }>({});
  const register = useCallback((key: "video" | "camera" | "microphone", element: HTMLElement | null) => {
    if (!element) return;
    setNodes((previous) => (previous[key] === element ? previous : { ...previous, [key]: element }));
  }, []);
  const [readiness, setReadiness] = useState<AssetsReadiness | null>(null);
  const [vision, setVision] = useState<VisionStatus>(OFF);
  const [microphone, setMicrophone] = useState<{ status: MicrophoneStatus; error?: string }>({ status: "off" });
  const [view, setView] = useState<AttentionView>({ source: "none", state: "neutral", confidence: 0 });
  const [diagnostics, setDiagnostics] = useState<Diagnostics | null>(null);
  const [lastClap, setLastClap] = useState<{ at: number; evidence: ClapDetected["evidence"] } | null>(null);
  const [tts, setTts] = useState<TtsInfo | null>(null);
  const clapConsent = storedClapListening.useValue();
  const clapStartsListening = storedClapStartsListening.useValue();

  useEffect(() => {
    hooksRef.current = hooks;
    sessionRef.current?.setInteraction(hooks.interaction);
  }, [hooks]);

  // The bundled assets are checked once per page (the heavy files load only on the camera press).
  useEffect(() => {
    let alive = true;
    void loadVisionAssets(VISION_BASE).then((result) => alive && setReadiness(result));
    return () => {
      alive = false;
    };
  }, []);

  // The adapter (engine first, labelled pointer/touch fallback) lives with the figure, with or
  // without the engine; it is the only thing that moves the figure's eyes and head.
  useEffect(() => {
    if (!avatar) return;
    const adapter = new MotionAdapter(avatar, { onChange: setView });
    adapterRef.current = adapter;
    return () => {
      adapter.stop();
      if (adapterRef.current === adapter) adapterRef.current = null;
    };
  }, [avatar]);

  // One engine session per mounted figure; released with it (stage closed, mode changed).
  useEffect(() => {
    const adapter = adapterRef.current;
    if (!avatar || !adapter || !readiness?.ready || !nodes.video || !nodes.camera || !nodes.microphone) return;
    const speaker = createAcknowledgementSpeaker(() => hooksRef.current.providerKey, setTts);
    speakerRef.current = speaker;
    const reaction = new VoiceReaction(speaker, (event) => {
      if (event.type === "start") hooksRef.current.onPlayback("start");
      else if (event.type === "end") hooksRef.current.onPlayback("end");
      else if (event.type === "unavailable") hooksRef.current.onPlayback("unavailable");
      else if (event.type === "error") hooksRef.current.onPlayback("error");
    });
    reactionRef.current = reaction;
    const session = new PerceptionSession({
      base: VISION_BASE,
      assets: readiness.assets,
      video: nodes.video,
      cameraIndicator: nodes.camera,
      microphoneIndicator: nodes.microphone,
      adapter,
      lowPower: avatar.isLowPower(),
      reducedMotion: typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches,
      onVision: setVision,
      onMicrophone: (status, error) => setMicrophone({ status, error }),
      onDiagnostics: setDiagnostics,
      onClap: (event) => {
        // Acknowledgement only: a short spoken "I'm listening." in the UI language. Never a tool, a send or listening by itself.
        setLastClap({ at: event.timestampMs, evidence: event.evidence });
        try {
          void reaction.react(acknowledgement(event, hooksRef.current.language));
        } catch {
          // below the engine's confidence floor: ignored
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
      setVision(OFF);
      setMicrophone({ status: "off" });
    };
  }, [avatar, readiness, nodes]);

  const pointer = useCallback((gaze: Gaze | null, source: "pointer" | "touch") => {
    if (adapterRef.current) adapterRef.current.pointerGaze(gaze, source);
    else avatar?.setGaze(gaze);
  }, [avatar]);

  const cameraRunning = vision.camera !== "off";
  const toggleCamera = () => (cameraRunning ? sessionRef.current?.stopCamera() : void sessionRef.current?.startCamera());
  const micRunning = microphone.status === "active" || microphone.status === "requesting";
  const toggleClap = () => {
    if (micRunning) {
      sessionRef.current?.stopClap();
      return;
    }
    storedClapListening.set("on");
    void sessionRef.current?.startClap();
  };
  const disableClap = () => {
    sessionRef.current?.stopClap();
    storedClapListening.set("off");
  };
  useEffect(() => {
    if (clapConsent === "off") sessionRef.current?.stopClap();
  }, [clapConsent]);

  const simulated = Boolean(vision.simulated);
  const cameraWords: Record<VisionStatus["camera"], string> = {
    off: t.off,
    requesting: t.requesting,
    denied: t.denied,
    unavailable: t.unavailable,
    tracking: t.tracking,
    lost: t.lost,
    error: f(t.cameraError, { detail: vision.message ?? "" }),
  };
  const unavailableReason = !readiness
    ? ""
    : readiness.ready
      ? ""
      : readiness.reason === "missing"
        ? t.assetsMissing
        : readiness.reason === "invalid"
          ? f(t.assetsInvalid, { detail: readiness.detail })
          : f(t.cameraError, { detail: readiness.detail });
  const attention =
    view.source === "hand" ? t.attentionHand : view.source === "face" ? t.attentionHead : view.source === "touch" ? t.attentionTouch : view.source === "pointer" ? t.attentionPointer : "";
  const micWords: Record<MicrophoneStatus, string> = {
    off: tc.off,
    requesting: tc.requesting,
    active: tc.active,
    error: /denied|NotAllowed|permission/i.test(microphone.error ?? "") ? tc.denied : f(tc.error, { detail: microphone.error ?? "" }),
  };

  return {
    pointer,
    register,
    camera: {
      available: Boolean(readiness?.ready),
      running: cameraRunning,
      state: vision.camera,
      text: cameraWords[vision.camera] + (simulated ? ` (${t.simulated})` : ""),
      buttonText: cameraRunning ? t.stop : t.on,
      privacy: readiness?.ready ? `${t.privacy} ${t.engine}` : unavailableReason || t.unavailable,
      toggle: toggleCamera,
    },
    clap: {
      available: Boolean(readiness?.ready),
      consent: clapConsent === "on",
      running: micRunning,
      status: microphone.status,
      text: micWords[microphone.status],
      buttonText: micRunning ? tc.stop : tc.listen,
      privacy: tc.privacy,
      toggle: toggleClap,
      disable: disableClap,
      startsListening: clapStartsListening === "on",
      setStartsListening: (on: boolean) => storedClapStartsListening.set(on ? "on" : "off"),
      last: lastClap,
      heardText: tc.heard,
      count: diagnostics?.clapCount ?? 0,
    },
    attention,
    diagnostics,
    tts,
    /** Plain-text Diagnostics for the owner: numbers and words only (no images, audio or landmarks). */
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
        ["vision", readiness ? (readiness.ready ? "assets verified" : `${readiness.reason}: ${readiness.detail}`) : "checking"],
        ["camera", vision.camera],
        ["camera.fps", diagnostics?.cameraFps ?? 0],
        ["camera.inferenceMs", diagnostics?.inferenceMs ?? "—"],
        ["camera.faceDetected", diagnostics?.faceDetected ?? false],
        ["camera.handDetected", diagnostics?.handDetected ?? false],
        ["attention", diagnostics?.attention ?? "neutral"],
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

export function CameraAttentionRow({ camera }: { camera: ReturnType<typeof useCameraAttention> }) {
  const dot = (state: string) =>
    cn(
      "inline-block h-2 w-2 rounded-full",
      state === "tracking" || state === "active"
        ? "bg-sky-400 shadow-[0_0_8px_rgba(56,189,248,0.9)]"
        : state === "lost"
          ? "bg-sky-700"
          : state === "requesting"
            ? "bg-amber-400"
            : state === "denied" || state === "error"
              ? "bg-red-400"
              : "bg-slate-500",
    );
  return (
    <div
      className="relative z-10 flex w-full max-w-2xl flex-col items-center gap-1 text-xs text-slate-300"
      data-testid="camera-attention"
      data-fps={camera.diagnostics?.cameraFps ?? 0}
      data-inference-ms={camera.diagnostics?.inferenceMs ?? ""}
      data-attention={camera.diagnostics?.attention ?? "neutral"}
      data-clap-count={camera.diagnostics?.clapCount ?? 0}
      data-tts-provider={camera.tts?.provider ?? ""}
    >
      {/* The engine draws into this hidden element; it never appears on screen. */}
      <video ref={(el) => camera.register("video", el)} className="hidden" muted playsInline aria-hidden />
      <p className="min-h-4 text-slate-200/80" aria-live="polite" data-testid="attention">
        {camera.attention}
      </p>
      <div className="flex flex-wrap items-center justify-center gap-3">
        <span className="flex items-center gap-1.5" role="status" data-testid="camera-state" data-camera={camera.camera.state}>
          <span className={dot(camera.camera.state)} aria-hidden />
          {camera.camera.text}
        </span>
        <button
          type="button"
          onClick={camera.camera.toggle}
          disabled={!camera.camera.available}
          className="rounded-full border border-slate-600 px-2.5 py-0.5 text-slate-100 transition-colors hover:border-sky-300 disabled:cursor-default disabled:opacity-50"
          data-testid="camera-toggle"
        >
          {camera.camera.buttonText}
        </button>
        <span ref={(el) => camera.register("camera", el)} className="text-[10px] uppercase tracking-wide text-slate-500" data-testid="camera-indicator" />
      </div>
      <div className="flex flex-wrap items-center justify-center gap-3">
        <span className="flex items-center gap-1.5" role="status" data-testid="clap-state" data-microphone={camera.clap.status}>
          <span className={dot(camera.clap.status)} aria-hidden />
          {camera.clap.text}
        </span>
        <button
          type="button"
          onClick={camera.clap.toggle}
          disabled={!camera.clap.available}
          className="rounded-full border border-slate-600 px-2.5 py-0.5 text-slate-100 transition-colors hover:border-sky-300 disabled:cursor-default disabled:opacity-50"
          data-testid="clap-toggle"
        >
          {camera.clap.buttonText}
        </button>
        <label className="flex items-center gap-1 text-[11px] text-slate-400">
          <input type="checkbox" checked={camera.clap.startsListening} onChange={(e) => camera.clap.setStartsListening(e.target.checked)} data-testid="clap-starts-listening" />
          {useI18nWord("startsListening")}
        </label>
        <span ref={(el) => camera.register("microphone", el)} className="text-[10px] uppercase tracking-wide text-slate-500" data-testid="microphone-indicator" />
        {camera.clap.last ? (
          <span className="text-amber-200" data-testid="clap-heard">
            {camera.clap.heardText} ×{camera.clap.count}
          </span>
        ) : null}
      </div>
      <p className="max-w-md text-center text-[11px] text-slate-400">{camera.camera.privacy}</p>
      <p className="max-w-md text-center text-[11px] text-slate-500">{camera.clap.privacy}</p>
      <DiagnosticsPanel report={camera.report} />
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

function useI18nWord(key: "startsListening"): string {
  const { m } = useI18n();
  return m.voice.clap[key];
}
