/**
 * Voice level (0..1) for the avatar, from a microphone or from EZO's own voice.
 * Pure helpers plus a tiny Web Audio meter.
 */

/** RMS of time-domain samples mapped from about -55 dBFS (silence) to -12 dBFS (loud speech). */
export function levelFromSamples(samples: Float32Array): number {
  let sum = 0;
  for (const sample of samples) sum += sample * sample;
  const rms = samples.length ? Math.sqrt(sum / samples.length) : 0;
  if (rms <= 0) return 0;
  const db = 20 * Math.log10(rms);
  return Math.min(1, Math.max(0, (db + 55) / 43));
}

/** Fast attack, slower release: the face reacts at once and settles gently. */
export function followLevel(current: number, target: number, dt: number): number {
  const rate = target > current ? 28 : 7;
  return current + (target - current) * (1 - Math.exp(-dt * rate));
}

/**
 * When the voice level is unknown (the browser's own speech has no audio tap), a
 * speech-like envelope keeps the face moving while EZO talks. It is animation only.
 */
export function syntheticSpeech(time: number): number {
  const syllables = Math.max(0, Math.sin(time * 11.5)) * (0.55 + 0.45 * Math.sin(time * 2.7));
  const phrases = 0.6 + 0.4 * Math.sin(time * 0.9);
  return Math.min(1, 0.15 + syllables * phrases * 0.85);
}

export interface LevelMeter {
  read(): number;
  close(): void;
}

type CapturableMedia = HTMLMediaElement & { captureStream?: () => MediaStream; mozCaptureStream?: () => MediaStream };

/**
 * Measures a microphone stream, or EZO's voice playing in a media element.
 *
 * A media element is measured through `captureStream()` so its sound is never rerouted
 * (rerouting through a suspended AudioContext would silence it). Call this once the
 * element is playing. Returns null where measuring is impossible (e.g. Safari media
 * elements); the avatar then animates speech on its own.
 */
export function createLevelMeter(source: MediaStream | HTMLMediaElement): LevelMeter | null {
  const Context = typeof window !== "undefined" ? (window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext) : undefined;
  if (!Context) return null;
  let stream: MediaStream | null = null;
  if (typeof MediaStream !== "undefined" && source instanceof MediaStream) stream = source;
  else {
    const media = source as CapturableMedia;
    try {
      stream = media.captureStream?.() ?? media.mozCaptureStream?.() ?? null;
    } catch {
      stream = null;
    }
  }
  if (!stream || stream.getAudioTracks().length === 0) return null;
  let context: AudioContext | null = null;
  try {
    context = new Context();
    void context.resume().catch(() => undefined);
    const analyser = context.createAnalyser();
    analyser.fftSize = 1024;
    context.createMediaStreamSource(stream).connect(analyser);
    const samples = new Float32Array(analyser.fftSize);
    const opened = context;
    return {
      read() {
        analyser.getFloatTimeDomainData(samples);
        return levelFromSamples(samples);
      },
      close() {
        void opened.close().catch(() => undefined);
      },
    };
  } catch {
    void context?.close().catch(() => undefined);
    return null;
  }
}
