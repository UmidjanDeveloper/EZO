/** Real PCM measurement and frame-rate-independent smoothing. Never invents speech amplitude. */
export function levelFromSamples(samples: Float32Array): number {
  let sum = 0;
  for (const sample of samples) if (Number.isFinite(sample)) sum += sample * sample;
  const rms = samples.length ? Math.sqrt(sum / samples.length) : 0;
  return rms > 0 ? Math.min(1, Math.max(0, (20 * Math.log10(rms) + 55) / 43)) : 0;
}
export function followLevel(current: number, target: number, dt: number): number {
  const safe = Math.min(1, Math.max(0, Number.isFinite(target) ? target : 0));
  return current + (safe - current) * (1 - Math.exp(-Math.max(0, dt) * (safe > current ? 28 : 7)));
}
export interface LevelMeter {
  read(): number;
  /** A running context and live audio track are required before claiming a measurement. */
  ready(): boolean;
  close(): void;
}
type CapturableMedia = HTMLMediaElement & { captureStream?: () => MediaStream; mozCaptureStream?: () => MediaStream };

/**
 * Tap a microphone or actual generated-audio playback without rerouting its output.
 * Unsupported media capture returns null, not a simulated waveform. The caller owns
 * the source stream; only the private capture tracks and audio graph are closed here.
 */
export function createLevelMeter(source: MediaStream | HTMLMediaElement): LevelMeter | null {
  const Context = typeof window !== "undefined" ? window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext : undefined;
  if (!Context) return null;
  const input = typeof MediaStream !== "undefined" && source instanceof MediaStream;
  let stream: MediaStream;
  if (input) stream = source as MediaStream;
  else {
    const media = source as CapturableMedia;
    try { stream = media.captureStream?.() ?? media.mozCaptureStream?.()!; } catch { return null; }
  }
  if (!stream || stream.getAudioTracks().length === 0) return null;
  let context: AudioContext | null = null;
  let closed = false;
  try {
    context = new Context({ latencyHint: "interactive" });
    void context.resume().catch(() => undefined);
    const analyser = context.createAnalyser();
    analyser.fftSize = 1024;
    analyser.smoothingTimeConstant = 0.65;
    const node = context.createMediaStreamSource(stream);
    node.connect(analyser); // deliberately NOT destination: no echo or duplicate playback
    const samples = new Float32Array(analyser.fftSize);
    const opened = context;
    return {
      read() { if (closed) return 0; analyser.getFloatTimeDomainData(samples); return levelFromSamples(samples); },
      ready() { return !closed && opened.state === "running" && stream.getAudioTracks().some((track) => track.readyState === "live" && !track.muted); },
      close() {
        if (closed) return;
        closed = true; node.disconnect(); analyser.disconnect();
        if (!input) stream.getTracks().forEach((track) => track.stop());
        void opened.close().catch(() => undefined);
      },
    };
  } catch { void context?.close().catch(() => undefined); return null; }
}
