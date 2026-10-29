/** Provenance-aware voice signal: microphone input can never pose as generated speech. */
export type VoiceChannel = "microphone" | "output";
export interface VoiceSignal {
  level: number;
  channel: VoiceChannel;
  measured: boolean;
  status: "idle" | "live" | "unavailable";
}
const IDLE: VoiceSignal = { level: 0, channel: "output", measured: false, status: "idle" };
let snapshot = IDLE;
const listeners = new Set<(signal: VoiceSignal) => void>();
const statusListeners = new Set<() => void>();
function publish(next: VoiceSignal) {
  const changed = snapshot.status !== next.status || snapshot.channel !== next.channel || snapshot.measured !== next.measured;
  snapshot = next;
  for (const listener of listeners) listener(next);
  if (changed) for (const listener of statusListeners) listener();
}
export function publishVoiceLevel(level: number, channel: VoiceChannel = "output") {
  publish({ level: Number.isFinite(level) ? Math.max(0, Math.min(1, level)) : 0, channel, measured: true, status: "live" });
}
export function publishVoiceUnavailable(channel: VoiceChannel = "output") {
  publish({ level: 0, channel, measured: false, status: "unavailable" });
}
export function resetVoiceSignal(channel?: VoiceChannel) {
  if (!channel || snapshot.channel === channel) publish(IDLE);
}
export function getVoiceSignal(): VoiceSignal { return snapshot; }
export function subscribeVoiceLevel(listener: (signal: VoiceSignal) => void): () => void {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}
export function subscribeVoiceStatus(listener: () => void): () => void {
  statusListeners.add(listener);
  return () => { statusListeners.delete(listener); };
}
