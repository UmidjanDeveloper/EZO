/**
 * The web app's perception wiring: where the bundled, SHA256-pinned vision assets live
 * (public/vision, prepared at build time by scripts/vision-assets.mjs), the clap consent
 * settings (off by default) and the acknowledgement voice through the real /api/voice/speak.
 * Nothing starts without the owner's own press; a clap never sends, runs or listens unless
 * "start listening after a clap" is on.
 */
import { AcknowledgementSpeaker } from "@ezo/perception-client";
import { api } from "./api";
import { createStoredValue } from "./stored-value";
import { publishVoiceLevel } from "./voice/level";
import { voiceVolume } from "./voice/engine";

export const VISION_BASE = "/vision/";

/** Clap listening consent: "on" only after the owner switched it on (and pressed Listen). */
export const storedClapListening = createStoredValue<"off" | "on">("ezo-clap-listening", "off", (v): v is "off" | "on" => v === "off" || v === "on");
/** After the spoken acknowledgement, start listening — only when the owner enabled it. */
export const storedClapStartsListening = createStoredValue<"off" | "on">("ezo-clap-starts-listening", "off", (v): v is "off" | "on" => v === "off" || v === "on");

export interface TtsInfo {
  provider: string | null;
  latencyMs: number;
  cached: boolean;
  at: number;
}

/** One speaker per page: clips cached per server voice setting + language. */
export function createAcknowledgementSpeaker(providerKey: () => string, onTts: (info: TtsInfo) => void): AcknowledgementSpeaker {
  return new AcknowledgementSpeaker({
    synthesize: (text, language, signal) => api.speakWithProvider(text, language, signal),
    cacheKey: providerKey,
    volume: voiceVolume,
    onLevel: publishVoiceLevel,
    onSynthesized: (info) => onTts({ ...info, at: Date.now() }),
  });
}
