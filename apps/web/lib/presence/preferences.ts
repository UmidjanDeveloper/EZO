import { createStoredValue } from "@/lib/stored-value";
import type { QualityProfile } from "@ezo/avatar";
export const storedQuality = createStoredValue<QualityProfile>("ezo-energy-quality", "auto", (v): v is QualityProfile => ["auto", "high", "balanced", "low"].includes(v));
export const storedMotion = createStoredValue<"system" | "reduced">("ezo-energy-motion", "system", (v): v is "system" | "reduced" => v === "system" || v === "reduced");
export const storedIntensity = createStoredValue<string>("ezo-energy-intensity", "0.8", (v): v is string => /^(0(\.\d+)?|1)$/.test(v));
export const storedCaptions = createStoredValue<"on" | "off">("ezo-voice-captions", "on", (v): v is "on" | "off" => v === "on" || v === "off");
