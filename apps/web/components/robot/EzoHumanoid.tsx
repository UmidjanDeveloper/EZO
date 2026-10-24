"use client";

import { EzoAvatar, toAvatarState, type Framing } from "@ezo/avatar";
import { cn } from "@ezo/ui";
import { useEffect, useRef, useSyncExternalStore } from "react";
import type { EzoState } from "@/lib/ezo-state";
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
}

/**
 * EZO's humanoid face: a WebGL particle figure (packages/avatar) that listens,
 * thinks and speaks, following the live voice level. Always drawn on its own
 * night backdrop; without WebGL the classic EzoPresence orb is shown instead.
 */
export function EzoHumanoid({ state, framing = "bust", className, label }: EzoHumanoidProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const avatarRef = useRef<EzoAvatar | null>(null);
  const stateRef = useRef(state);
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
    return () => {
      unsubscribe();
      avatar.destroy();
      avatarRef.current = null;
    };
  }, [framing, supported]);

  if (!supported) {
    return <EzoPresence state={state} size={framing === "head" ? 200 : 290} className={className} />;
  }
  return (
    <div
      className={cn("ezo-night overflow-hidden", className)}
      data-testid="ezo-humanoid"
      data-state={state}
      role="img"
      aria-label={label ?? "EZO"}
    >
      <canvas ref={canvasRef} className="absolute inset-0 h-full w-full" />
    </div>
  );
}
