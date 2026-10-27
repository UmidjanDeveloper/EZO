import { createLevelMeter, type LevelMeter } from "@ezo/avatar";
import type { AcknowledgementIntent, AcknowledgementPlayer, Language, PlaybackEvent } from "@ezo/face-tracking";

export interface SpeakerOptions {
  /** The app's authenticated /api/voice/speak call; rejects when no provider is configured. */
  synthesize: (text: string, language: Language, signal: AbortSignal) => Promise<{ audio: Blob; provider: string | null }>;
  /** Changes when the server's voice/provider setting changes; the cache is dropped then. */
  cacheKey: () => string;
  volume?: () => number;
  /** The real playback level 0..1 while the clip plays (drives the figure's jaw). */
  onLevel?: (level: number) => void;
  /** Provider and latency of the last synthesis, for Diagnostics. */
  onSynthesized?: (info: { provider: string | null; latencyMs: number; cached: boolean; language: Language }) => void;
}

/**
 * Plays EZO's spoken acknowledgement ("Eshitaman seni." / "I'm listening." / "Я тебя слушаю.")
 * through the app's real TTS endpoint and a real <audio> element, measuring the playback
 * level for the figure. Clips are cached per voice setting + language after the first
 * synthesis so later claps answer instantly; no provider means "unavailable", never a
 * pretended playback. Nothing here starts listening or any tool.
 */
export class AcknowledgementSpeaker implements AcknowledgementPlayer {
  private readonly options: SpeakerOptions;
  private cache = new Map<string, Blob>();
  private cacheOwner = "";
  private current: HTMLAudioElement | null = null;

  constructor(options: SpeakerOptions) {
    this.options = options;
  }

  /** Drops the cache when the voice setting changed. */
  private clip(language: Language): Blob | null {
    const owner = this.options.cacheKey();
    if (owner !== this.cacheOwner) {
      this.cache.clear();
      this.cacheOwner = owner;
    }
    return this.cache.get(language) ?? null;
  }

  cachedLanguages(): Language[] {
    return [...this.cache.keys()] as Language[];
  }

  async play(intent: AcknowledgementIntent, signal: AbortSignal, onPlayback: (event: PlaybackEvent) => void): Promise<void> {
    let blob = this.clip(intent.language);
    const started = performance.now();
    if (!blob) {
      const result = await this.options.synthesize(intent.text, intent.language, signal);
      blob = result.audio;
      if (!blob || blob.size === 0) throw new Error("empty audio");
      this.cache.set(intent.language, blob);
      this.options.onSynthesized?.({ provider: result.provider, latencyMs: performance.now() - started, cached: false, language: intent.language });
    } else this.options.onSynthesized?.({ provider: null, latencyMs: 0, cached: true, language: intent.language });
    if (signal.aborted) return;
    this.stop();
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    audio.volume = Math.min(1, Math.max(0, this.options.volume?.() ?? 1));
    this.current = audio;
    const ref: { meter: LevelMeter | null; frame: number } = { meter: null, frame: 0 };
    const done = new Promise<void>((resolve, reject) => {
      audio.onplaying = () => {
        onPlayback({ type: "start", timestampMs: performance.now() });
        ref.meter ??= createLevelMeter(audio);
        const tick = () => {
          if (!ref.meter || this.current !== audio) return;
          const level = ref.meter.read();
          this.options.onLevel?.(level);
          onPlayback({ type: "level", level, timestampMs: performance.now() });
          ref.frame = requestAnimationFrame(tick);
        };
        if (ref.meter) ref.frame = requestAnimationFrame(tick);
      };
      audio.onended = () => resolve();
      audio.onerror = () => reject(new Error("playback failed"));
      signal.addEventListener("abort", () => resolve(), { once: true });
    });
    try {
      await audio.play();
      await done;
    } finally {
      cancelAnimationFrame(ref.frame);
      ref.meter?.close();
      this.options.onLevel?.(0);
      if (this.current === audio) {
        audio.pause();
        this.current = null;
      }
      URL.revokeObjectURL(url);
      onPlayback({ type: "end", timestampMs: performance.now() });
    }
  }

  stop(): void {
    if (this.current) {
      this.current.pause();
      this.current = null;
    }
  }
}
