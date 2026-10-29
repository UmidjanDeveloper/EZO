/**
 * Voice engines for the voice stage.
 *
 * - "server": the microphone is recorded in the browser and sent to EZO's API,
 *   which transcribes it with a configured provider (VoiceStudio, OpenAI…);
 *   replies are read with the server voice.
 * - "browser": the Web Speech API (Chrome, Edge, Safari).
 *
 * Speaking always falls back to the browser voice if the server voice fails,
 * and a failed server transcription makes the stage use the browser for the
 * following turns. Nothing is faked: unsupported paths report an error.
 */

import { createStoredValue } from "@/lib/stored-value";
import type { LanguageCode, VoiceStatus } from "@ezo/shared";
import { ApiError } from "@ezo/shared";
import { api } from "../api";
import { listenOnce, speak as browserSpeak, speechRecognitionSupported, stopSpeaking, type ListenHandlers } from "../speech";
import { createLevelMeter, levelFromSamples } from "@ezo/avatar";
import { publishVoiceLevel, publishVoiceUnavailable, resetVoiceSignal } from "./level";
import { DEFAULT_VAD, rmsOf, speakingSeconds, vadStart, vadStep } from "./vad";

export type EngineKind = "server" | "browser";

/**
 * Start listening; returns a function that cancels (discarding the recording).
 * `language` null means "any of EZO's languages" (server recognition only).
 */
export type Listen = (language: LanguageCode | null, handlers: ListenHandlers) => () => void;

const LANGUAGES: readonly string[] = ["uz", "en", "ru"];
const asLanguage = (value: string | null | undefined): LanguageCode | null =>
  value && LANGUAGES.includes(value) ? (value as LanguageCode) : null;

export function serverRecordingSupported(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof window.MediaRecorder !== "undefined" &&
    Boolean(navigator.mediaDevices?.getUserMedia)
  );
}

/** Which listener to use for this turn. */
export function pickListener(status: VoiceStatus | null, serverFailed: boolean): EngineKind | null {
  if (status && status.speech_to_text.length > 0 && !serverFailed && serverRecordingSupported()) return "server";
  if (speechRecognitionSupported()) return "browser";
  return null;
}

const RECORDER_TYPES = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/mp4"];

export function pickRecorderType(isSupported: (type: string) => boolean): string | undefined {
  return RECORDER_TYPES.find((type) => isSupported(type));
}

function extensionFor(type: string): string {
  if (type.includes("ogg")) return "ogg";
  if (type.includes("mp4")) return "m4a";
  return "webm";
}

/** Error codes reported through `onEnd`, matching the browser recogniser's where possible. */
export const SERVER_FAILED = "server-failed";

/**
 * VAD for exam-style answers: an IELTS Part 2 long turn lasts up to two minutes with
 * natural pauses, so a short silence must not end the recording.
 */
export const LONG_ANSWER_VAD = { ...DEFAULT_VAD, endSilenceMs: 3500, noSpeechMs: 12_000, maxMs: 130_000 };

/** Record one utterance (until a pause) and transcribe it on the server. */
export const listenWithServer = (
  language: LanguageCode | null,
  handlers: ListenHandlers,
  vadConfig: typeof DEFAULT_VAD = DEFAULT_VAD,
): (() => void) => {
  let cancelled = false;
  let finished = false;
  let cleanup = () => undefined as void;

  const end = (error: string | null) => {
    if (finished) return;
    finished = true;
    cleanup();
    handlers.onEnd(error);
  };

  void (async () => {
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
    } catch (error) {
      end(error instanceof DOMException && error.name === "NotAllowedError" ? "not-allowed" : "audio-capture");
      return;
    }
    if (cancelled) {
      stream.getTracks().forEach((track) => track.stop());
      return;
    }
    const type = pickRecorderType((candidate) => MediaRecorder.isTypeSupported(candidate));
    const recorder = new MediaRecorder(stream, type ? { mimeType: type } : undefined);
    const chunks: Blob[] = [];
    const context = new AudioContext();
    void context.resume().catch(() => undefined); // may start suspended without a fresh gesture
    const analyser = context.createAnalyser();
    analyser.fftSize = 2048;
    context.createMediaStreamSource(stream).connect(analyser);
    const samples = new Float32Array(analyser.fftSize);
    let vad = vadStart(performance.now());
    let heardSpeech = false;

    const timer = window.setInterval(() => {
      analyser.getFloatTimeDomainData(samples);
      publishVoiceLevel(levelFromSamples(samples), "microphone");
      const [next, action] = vadStep(vad, rmsOf(samples), performance.now(), vadConfig);
      vad = next;
      if (vad.speechAt !== null && !heardSpeech) {
        heardSpeech = true;
        handlers.onInterim("…");
      }
      if (action !== "continue" && recorder.state === "recording") recorder.stop();
    }, 100);

    cleanup = () => {
      window.clearInterval(timer);
      resetVoiceSignal("microphone");
      if (recorder.state === "recording") recorder.stop();
      stream.getTracks().forEach((track) => track.stop());
      void context.close().catch(() => undefined);
    };

    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) chunks.push(event.data);
    };
    recorder.onstop = async () => {
      if (cancelled || finished) return;
      window.clearInterval(timer);
      if (!heardSpeech || chunks.length === 0) {
        end("no-speech");
        return;
      }
      const mime = recorder.mimeType || type || "audio/webm";
      const blob = new Blob(chunks, { type: mime });
      handlers.onRecognizing?.(); // the recording is over; the server is turning it into words
      try {
        const result = await api.transcribe(blob, `speech.${extensionFor(mime)}`, language);
        if (cancelled) return;
        const text = result.text.trim();
        if (text) handlers.onFinal(text, { speechSeconds: speakingSeconds(vad), language: asLanguage(result.language) });
        end(text ? null : "no-speech");
      } catch (error) {
        if (cancelled) return;
        end(error instanceof ApiError && error.code === "bad_audio" ? "no-speech" : SERVER_FAILED);
      }
    };
    recorder.start(250);
  })();

  return () => {
    cancelled = true;
    if (!finished) {
      finished = true;
      cleanup();
    }
  };
};

/** The browser recogniser needs one fixed language; callers resolve "auto" before this. */
export const listenWithBrowser: Listen = (language, handlers) => {
  publishVoiceUnavailable("microphone");
  return listenOnce(language ?? "uz", { ...handlers, onEnd: (error) => { resetVoiceSignal("microphone"); handlers.onEnd(error); } });
};

let currentAudio: HTMLAudioElement | null = null;
/** EZO's voice volume 0..1 (the stage slider); applied to every server-voice playback. */
export const storedVoiceVolume = createStoredValue<string>("ezo-voice-volume", "1", (value): value is string => /^(0(\.\d+)?|1)$/.test(value));
export function voiceVolume(): number {
  const value = Number(storedVoiceVolume.get());
  return Number.isFinite(value) ? Math.min(1, Math.max(0, value)) : 1;
}
let currentRequest: AbortController | null = null;
let playbackGeneration = 0;
export const storedVoiceRate = createStoredValue<string>("ezo-voice-rate", "1", (v): v is string => /^(0\.[7-9]\d*|1(\.[0-2]\d*)?)$/.test(v) && Number(v) >= 0.7 && Number(v) <= 1.3);
export function voiceRate(): number { return Number(storedVoiceRate.get()) || 1; }
export interface PlaybackHooks { onStart?: (engine: EngineKind) => void }
export function setVoiceVolume(value: number): void {
  storedVoiceVolume.set(String(Math.max(0, Math.min(1, value))));
  if (currentAudio) currentAudio.volume = voiceVolume();
}

/** Stop whatever EZO is saying (server or browser voice). */
export function stopVoice(): void {
  playbackGeneration++;
  resetVoiceSignal("output");
  currentRequest?.abort();
  currentRequest = null;
  if (currentAudio) {
    currentAudio.pause();
    currentAudio.src = "";
    currentAudio = null;
  }
  stopSpeaking();
}

/** Read generated audio. Speaking starts on the actual playback event, not on synthesis request. */
export async function speakReply(text: string, language: LanguageCode, status: VoiceStatus | null, hooks: PlaybackHooks = {}): Promise<EngineKind> {
  stopVoice();
  const generation = playbackGeneration;
  if (status && status.text_to_speech.length > 0) {
    const controller = new AbortController();
    currentRequest = controller;
    try {
      const audioBlob = await api.speak(text, language, controller.signal);
      if (controller.signal.aborted || generation !== playbackGeneration) return "server";
      await playBlob(audioBlob, generation, () => hooks.onStart?.("server"));
      return "server";
    } catch {
      if (controller.signal.aborted || generation !== playbackGeneration) return "server";
    } finally { if (currentRequest === controller) currentRequest = null; }
  }
  if (generation !== playbackGeneration) return "browser";
  publishVoiceUnavailable("output");
  await browserSpeak(text, language, { volume: voiceVolume(), rate: voiceRate(), onStart: () => hooks.onStart?.("browser") });
  if (generation === playbackGeneration) resetVoiceSignal("output");
  return "browser";
}

function playBlob(blob: Blob, generation: number, onStart: () => void): Promise<void> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    audio.volume = voiceVolume();
    currentAudio = audio;
    let frame = 0;
    let meter: ReturnType<typeof createLevelMeter> = null;
    let finished = false;
    const tick = () => {
      if (finished || generation !== playbackGeneration) return;
      if (meter?.ready()) publishVoiceLevel(meter.read(), "output");
      else publishVoiceUnavailable("output");
      frame = requestAnimationFrame(tick);
    };
    audio.onplaying = () => {
      if (finished || generation !== playbackGeneration) { audio.pause(); return; }
      meter ??= createLevelMeter(audio);
      if (meter) frame = requestAnimationFrame(tick);
      else publishVoiceUnavailable("output");
      onStart();
    };
    const done = (error?: unknown) => {
      if (finished) return;
      finished = true;
      cancelAnimationFrame(frame); meter?.close(); meter = null;
      audio.onplaying = audio.onended = audio.onpause = audio.onerror = null;
      audio.pause();
      URL.revokeObjectURL(url);
      if (currentAudio === audio) { currentAudio = null; resetVoiceSignal("output"); }
      if (error) reject(error); else resolve();
    };
    audio.onended = () => done();
    audio.onpause = () => done();
    audio.onerror = () => done(new Error("audio playback failed"));
    audio.play().catch(done);
  });
}
