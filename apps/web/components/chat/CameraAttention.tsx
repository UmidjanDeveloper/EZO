"use client";

import { AttentionDriver, type EzoAvatar, type Gaze, type MotionIntent, type VisionStatus } from "@ezo/avatar";
import { cn } from "@ezo/ui";
import { useCallback, useEffect, useRef, useState } from "react";
import { useI18n } from "@/lib/i18n/context";
import { sensingProvider, type SensingSession } from "@/lib/sensing";

const OFF: VisionStatus = { camera: "off", faces: 0, hands: 0, since: 0 };

/**
 * Camera attention for the voice stage: EZO looks at the person (and at a raised hand)
 * through the sensing engine, only after an explicit press, with a truthful status, a
 * clear stop and a labelled pointer/touch fallback. Nothing is recorded or uploaded.
 */
export function useCameraAttention(avatar: EzoAvatar | null) {
  const { m } = useI18n();
  const t = m.voice.camera;
  const driverRef = useRef<AttentionDriver | null>(null);
  const sessionRef = useRef<SensingSession | null>(null);
  const generation = useRef(0);
  const [vision, setVision] = useState<VisionStatus>(OFF);
  const [running, setRunning] = useState(false);
  const [intent, setIntent] = useState<MotionIntent>({ kind: "rest", source: "none" });
  const provider = sensingProvider();

  const stop = useCallback(() => {
    generation.current += 1;
    sessionRef.current?.stop();
    sessionRef.current = null;
    setRunning(false);
    driverRef.current?.headFrame(null);
    driverRef.current?.handFrame(null);
    const next = { ...OFF, since: performance.now() };
    driverRef.current?.setVision(next);
    setVision(next);
  }, []);

  // One driver per avatar; it is released with the avatar (stage closed, mode changed).
  useEffect(() => {
    if (!avatar) return;
    const driver = new AttentionDriver(avatar, { onIntent: setIntent });
    driverRef.current = driver;
    const onVisibility = () => {
      driver.setVisible(!document.hidden);
      if (document.hidden) stop();
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      stop();
      driver.stop();
      driverRef.current = null;
    };
  }, [avatar, stop]);

  const start = useCallback(async () => {
    const engine = sensingProvider();
    if (!engine || sessionRef.current || !driverRef.current) return;
    const mine = ++generation.current;
    const video = document.createElement("video");
    video.muted = true;
    video.playsInline = true;
    const requesting: VisionStatus = { camera: "requesting", faces: 0, hands: 0, since: performance.now(), simulated: engine.simulated };
    driverRef.current.setVision(requesting);
    setVision(requesting);
    try {
      const session = await engine.start({
        video,
        onStatus: (status) => {
          if (mine !== generation.current) return;
          const next = { ...status, simulated: engine.simulated || status.simulated };
          driverRef.current?.setVision(next);
          setVision(next);
        },
        onHead: (frame) => driverRef.current?.headFrame(frame),
        onHand: (hand) => driverRef.current?.handFrame(hand),
      });
      if (mine !== generation.current || document.hidden) {
        session.stop();
        return;
      }
      sessionRef.current = session;
      setRunning(true);
    } catch (error) {
      if (mine !== generation.current) return;
      const next: VisionStatus = { camera: "error", faces: 0, hands: 0, since: performance.now(), message: (error as Error).message, simulated: engine.simulated };
      driverRef.current?.setVision(next);
      setVision(next);
    }
  }, []);

  const pointer = useCallback((gaze: Gaze | null, source: "pointer" | "touch") => driverRef.current?.pointerGaze(gaze, source), []);

  const words: Record<VisionStatus["camera"], string> = {
    off: t.off,
    requesting: t.requesting,
    denied: t.denied,
    unavailable: t.unavailable,
    tracking: t.tracking,
    lost: t.lost,
    error: vision.message ?? t.denied,
  };
  const attention =
    intent.kind !== "look"
      ? ""
      : intent.source === "hand"
        ? t.attentionHand
        : intent.source === "head"
          ? t.attentionHead
          : intent.source === "touch"
            ? t.attentionTouch
            : t.attentionPointer;
  const simulatedNote = vision.simulated && intent.kind === "look" && (intent.source === "hand" || intent.source === "head") ? ` — ${t.simulated}` : "";

  return {
    pointer,
    running,
    vision,
    attention: attention + simulatedNote,
    statusText: words[vision.camera] + (vision.simulated ? ` (${t.simulated})` : ""),
    available: Boolean(provider),
    toggle: () => (running ? stop() : void start()),
    buttonText: running ? t.stop : t.on,
    privacy: provider ? t.privacy : t.unavailable,
    activeLabel: t.active,
  };
}

export function CameraAttentionRow({ camera }: { camera: ReturnType<typeof useCameraAttention> }) {
  return (
    <div className="relative z-10 flex w-full max-w-2xl flex-col items-center gap-1 text-xs text-slate-300" data-testid="camera-attention">
      <p className="min-h-4 text-slate-200/80" aria-live="polite" data-testid="attention">
        {camera.attention}
      </p>
      <div className="flex items-center gap-3">
        <span className="flex items-center gap-1.5" role="status" data-testid="camera-state" data-camera={camera.vision.camera}>
          <span
            className={cn(
              "inline-block h-2 w-2 rounded-full",
              camera.vision.camera === "tracking" || camera.vision.camera === "lost"
                ? "bg-sky-400 shadow-[0_0_8px_rgba(56,189,248,0.9)]"
                : camera.vision.camera === "requesting"
                  ? "bg-amber-400"
                  : camera.vision.camera === "denied" || camera.vision.camera === "error"
                    ? "bg-red-400"
                    : "bg-slate-500",
            )}
            aria-hidden
          />
          {camera.statusText}
        </span>
        <button
          type="button"
          onClick={camera.toggle}
          disabled={!camera.available}
          title={camera.available ? "" : camera.privacy}
          className="rounded-full border border-slate-600 px-2.5 py-0.5 text-slate-100 transition-colors hover:border-sky-300 disabled:cursor-default disabled:opacity-50"
          data-testid="camera-toggle"
        >
          {camera.buttonText}
        </button>
      </div>
      <p className="max-w-md text-center text-[11px] text-slate-400">{camera.privacy}</p>
    </div>
  );
}
