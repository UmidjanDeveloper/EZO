/**
 * The web app's clap wiring: the clap consent settings (off by default) and the
 * acknowledgement voice through the real /api/voice/speak.
 * Nothing starts without the owner's own press; a clap never sends, runs or listens unless
 * "start listening after a clap" is on.
 */
import { AcknowledgementSpeaker } from "@ezo/perception-client";
import { api } from "./api";
import { createStoredValue } from "./stored-value";
import { publishVoiceLevel, publishVoiceUnavailable, resetVoiceSignal } from "./voice/level";
import { voiceVolume } from "./voice/engine";

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
    onLevel: (level, measured) => { if (measured) publishVoiceLevel(level, "output"); else if (level === 0) resetVoiceSignal("output"); else publishVoiceUnavailable("output"); },
    onSynthesized: (info) => onTts({ ...info, at: Date.now() }),
  });
}

/** The chosen conversation language wins. */
export function acknowledgementLanguage(choice: "auto" | "uz" | "en" | "ru", lastHeard: "uz" | "en" | "ru" | null, ui: "uz" | "en" | "ru") {
  return choice === "auto" ? lastHeard ?? ui : choice;
}
