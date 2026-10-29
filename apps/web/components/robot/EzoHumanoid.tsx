"use client";

import { createVoiceFrame, EzoAvatar, toAvatarState, type AvatarState, type Framing, type Gaze, type QualityProfile, type VoiceFrame } from "@ezo/avatar";
import { cn } from "@ezo/ui";
import { useEffect, useMemo, useRef } from "react";
import type { EzoState } from "@/lib/ezo-state";
import { useI18n } from "@/lib/i18n/context";
import { storedIntensity, storedMotion, storedQuality } from "@/lib/presence/preferences";
import { getVoiceSignal, subscribeVoiceLevel } from "@/lib/voice/level";

interface EzoHumanoidProps {
  state: EzoState;
  framing?: Framing;
  /** Kept for source compatibility; every profile renders the energy figure. */
  style?: "energy";
  className?: string;
  label?: string;
  frame?: boolean;
  followPointer?: boolean;
  quality?: QualityProfile;
  onPointerGaze?: (gaze: Gaze | null, source: "pointer" | "touch") => void;
  onAvatar?: (avatar: EzoAvatar | null) => void;
}

/** GPU energy contours with the same anatomical still drawing on the 2D fallback. */
export function EzoHumanoid({ state, framing = "bust", className, label, frame = false, followPointer = false, quality: qualityOverride, onPointerGaze, onAvatar }: EzoHumanoidProps) {
  const { m } = useI18n();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const frameRef = useRef<HTMLDivElement>(null);
  const avatarRef = useRef<EzoAvatar | null>(null);
  const stateRef = useRef(state);
  const callbacks = useRef({ onAvatar, onPointerGaze });
  const labels = useMemo(() => words(m), [m]);
  const quality = storedQuality.useValue();
  const motion = storedMotion.useValue();
  const intensity = storedIntensity.useValue();
  const selectedQuality = qualityOverride ?? quality;

  useEffect(() => { stateRef.current = state; avatarRef.current?.setState(toAvatarState(state)); }, [state]);
  useEffect(() => { callbacks.current = { onAvatar, onPointerGaze }; }, [onAvatar, onPointerGaze]);

  useEffect(() => { avatarRef.current?.setQuality(selectedQuality); }, [selectedQuality]);
  useEffect(() => { avatarRef.current?.setMotionPreference(motion); }, [motion]);
  useEffect(() => { avatarRef.current?.setIntensity(Number(intensity)); }, [intensity]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const avatar = new EzoAvatar(canvas, {
      framing, style: "energy", quality: selectedQuality,
      reducedMotion: motion === "reduced" ? true : undefined,
      intensity: Number(intensity),

    });
    avatar.setState(toAvatarState(stateRef.current));
    avatarRef.current = avatar;
    callbacks.current.onAvatar?.(avatar);
    const applySignal = (signal: ReturnType<typeof getVoiceSignal>) => {
      if (signal.measured) avatar.setLevel(signal.level, signal.channel);
    };
    applySignal(getVoiceSignal());
    const unsubscribe = subscribeVoiceLevel(applySignal);
    let voiceFrame: VoiceFrame | null = null;
    if (frame && frameRef.current) { voiceFrame = createVoiceFrame(frameRef.current, { showWord: false }); voiceFrame.follow(avatar); }
    return () => {
      unsubscribe(); voiceFrame?.destroy(); avatar.destroy(); avatarRef.current = null;
      callbacks.current.onAvatar?.(null);
    };
    // Preferences update in place; never allocate a second renderer for a slider change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [framing, frame]);

  const onPointer = followPointer ? (event: React.PointerEvent<HTMLDivElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    const gaze = { yaw: ((event.clientX - rect.left) / rect.width) * 2 - 1, pitch: (1 - (event.clientY - rect.top) / rect.height) * 0.6 };
    if (callbacks.current.onPointerGaze) callbacks.current.onPointerGaze(gaze, event.pointerType === "touch" ? "touch" : "pointer");
    else avatarRef.current?.setGaze(gaze);
  } : undefined;

  return (
    <div className={cn("ezo-energy overflow-hidden bg-black", className)} data-testid="ezo-humanoid" data-state={state} data-style="energy"
      role="img" aria-label={`EZO — ${label ?? labels[toAvatarState(state)]}`}
      onPointerMove={onPointer} onPointerLeave={followPointer ? () => {
        if (callbacks.current.onPointerGaze) callbacks.current.onPointerGaze(null, "pointer");
        else avatarRef.current?.setGaze(null);
      } : undefined}>
      <canvas ref={canvasRef} className="absolute inset-0 h-full w-full" aria-hidden="true" />
      {frame ? <div ref={frameRef} className="pointer-events-none absolute inset-0" data-testid="voice-frame" /> : null}
    </div>
  );
}

function words(m: ReturnType<typeof useI18n>["m"]): Record<AvatarState, string> {
  return { idle: m.presence.idle, listening: m.presence.listening, recognizing: m.presence.recognizing, thinking: m.presence.thinking, working: m.presence.working, speaking: m.presence.speaking, success: m.presence.completed, error: m.presence.error, offline: m.presence.offline };
}
