/**
 * Live voice level (0..1) for EZO's humanoid: the microphone while listening,
 * EZO's own voice while speaking. A tiny publish/subscribe channel so the voice
 * engine and the avatar stay independent.
 */
type Listener = (level: number) => void;

const listeners = new Set<Listener>();

export function publishVoiceLevel(level: number): void {
  for (const listener of listeners) listener(level);
}

export function subscribeVoiceLevel(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
