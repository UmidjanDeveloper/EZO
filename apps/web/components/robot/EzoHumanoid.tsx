"use client";

import { createVoiceFrame, EzoAvatar, toAvatarState, type AvatarState, type Framing, type VoiceFrame } from "@ezo/avatar";
import { cn } from "@ezo/ui";
import { useEffect, useMemo, useRef, useSyncExternalStore } from "react";
import type { EzoState } from "@/lib/ezo-state";
import { useI18n } from "@/lib/i18n/context";
import { subscribeVoiceLevel } from "@/lib/voice/level";
import { EzoPresence } from "./EzoPresence";

let webglSupport: boolean | null = null;
const noSubscription = () => () => undefined;
const supportedSnapshot = () => (webglSupport ??= EzoAvatar.supported());

interface EzoHumanoidProps {
  state: EzoState;
  /** "bust": head and shoulders on the voice stage; "head": a compact face. */
  framing?: Framing;
  /** Size and position (e.g. "absolute inset-0" or "relative h-56 w-56"). */
  className?: string;
  /** Accessible name, e.g. the current status. */
  label?: string;
  /** The voice frame: ring, equaliser following the real level, and the state word. */
  frame?: boolean;
  /** EZO turns its head towards the pointer (mouse or touch) over the figure. */
  followPointer?: boolean;
}

/**
 * EZO's humanoid face: a WebGL particle figure (packages/avatar) that listens,
 * thinks and speaks, following the live voice level. Always drawn on its own
 * night backdrop; without WebGL the classic EzoPresence orb is shown instead.
 */
export function EzoHumanoid({ state, framing = "bust", className, label, frame = false, followPointer = false }: EzoHumanoidProps) {
  const { m } = useI18n();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const frameRef = useRef<HTMLDivElement>(null);
  const avatarRef = useRef<EzoAvatar | null>(null);
  const stateRef = useRef(state);
  const labels = useMemo(() => words(m), [m]);
  const supported = useSyncExternalStore(noSubscription, supportedSnapshot, () => true);

  useEffect(() => {
    stateRef.current = state;
    avatarRef.current?.setState(toAvatarState(state));
  }, [state]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !supported) return;
    const avatar = new EzoAvatar(canvas, { framing });
    avatar.setState(toAvatarState(stateRef.current));
    avatarRef.current = avatar;
    const unsubscribe = subscribeVoiceLevel((level) => avatar.setLevel(level));
    let voiceFrame: VoiceFrame | null = null;
    if (frame && frameRef.current) {
      voiceFrame = createVoiceFrame(frameRef.current, { showWord: false });
      voiceFrame.follow(avatar);
    }
    return () => {
      unsubscribe();
      voiceFrame?.destroy();
      avatar.destroy();
      avatarRef.current = null;
    };
  }, [framing, frame, supported]);

  const onPointer = followPointer
    ? (event: React.PointerEvent<HTMLDivElement>) => {
        const rect = event.currentTarget.getBoundingClientRect();
        const x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
        const y = 1 - ((event.clientY - rect.top) / rect.height) * 2;
        avatarRef.current?.setGaze({ yaw: x, pitch: y * 0.6 });
      }
    : undefined;

  if (!supported) {
    return <EzoPresence state={state} size={framing === "head" ? 200 : 290} className={className} />;
  }
  return (
    <div
      className={cn("ezo-night overflow-hidden", className)}
      data-testid="ezo-humanoid"
      data-state={state}
      role="img"
      aria-label={`EZO — ${label ?? labels[toAvatarState(state)]}`}
      onPointerMove={onPointer}
      onPointerLeave={followPointer ? () => avatarRef.current?.setGaze(null) : undefined}
    >
      {/* One accessible image: the wrapper names EZO and the state; the canvas stays decorative. */}
      <canvas ref={canvasRef} className="absolute inset-0 h-full w-full" aria-hidden="true" />
      {frame ? <div ref={frameRef} className="pointer-events-none absolute inset-0" data-testid="voice-frame" /> : null}
    </div>
  );
}

/** Accessible names for the figure's own states, in the UI language. */
function words(m: ReturnType<typeof useI18n>["m"]): Record<AvatarState, string> {
  return {
    idle: m.presence.idle,
    listening: m.presence.listening,
    recognizing: m.presence.recognizing,
    thinking: m.presence.thinking,
    working: m.presence.working,
    speaking: m.presence.speaking,
    success: m.presence.completed,
    error: m.presence.error,
    offline: m.presence.offline,
  };
}
