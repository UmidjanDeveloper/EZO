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
import { publishVoiceLevel } from "./level";
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
      publishVoiceLevel(levelFromSamples(samples));
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
      publishVoiceLevel(0);
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
export const listenWithBrowser: Listen = (language, handlers) => listenOnce(language ?? "uz", handlers);

let currentAudio: HTMLAudioElement | null = null;
/** EZO's voice volume 0..1 (the stage slider); applied to every server-voice playback. */
export const storedVoiceVolume = createStoredValue<string>("ezo-voice-volume", "1", (value): value is string => /^(0(\.\d+)?|1)$/.test(value));
export function voiceVolume(): number {
  const value = Number(storedVoiceVolume.get());
  return Number.isFinite(value) ? Math.min(1, Math.max(0, value)) : 1;
}
let currentRequest: AbortController | null = null;

/** Stop whatever EZO is saying (server or browser voice). */
export function stopVoice(): void {
  currentRequest?.abort();
  currentRequest = null;
  if (currentAudio) {
    currentAudio.pause();
    currentAudio.src = "";
    currentAudio = null;
  }
  stopSpeaking();
}

/**
 * Read a reply aloud: the server voice when available, otherwise (or if it
 * fails) the browser voice. Resolves with the engine that spoke.
 */
export async function speakReply(text: string, language: LanguageCode, status: VoiceStatus | null): Promise<EngineKind> {
  if (status && status.text_to_speech.length > 0) {
    const controller = new AbortController();
    currentRequest = controller;
    try {
      const audioBlob = await api.speak(text, language, controller.signal);
      if (controller.signal.aborted) return "server";
      await playBlob(audioBlob);
      return "server";
    } catch {
      if (controller.signal.aborted) return "server";
      // Fall through to the browser voice.
    } finally {
      if (currentRequest === controller) currentRequest = null;
    }
  }
  await browserSpeak(text, language);
  return "browser";
}

function playBlob(blob: Blob): Promise<void> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    audio.volume = voiceVolume();
    currentAudio = audio;
    let frame = 0;
    let meter: ReturnType<typeof createLevelMeter> = null;
    audio.onplaying = () => {
      // EZO's humanoid follows its own voice (where the browser can measure it).
      meter ??= createLevelMeter(audio);
      const tick = () => {
        if (!meter) return;
        publishVoiceLevel(meter.read());
        frame = requestAnimationFrame(tick);
      };
      if (meter && !frame) frame = requestAnimationFrame(tick);
    };
    const done = (error?: unknown) => {
      cancelAnimationFrame(frame);
      meter?.close();
      meter = null;
      publishVoiceLevel(0);
      URL.revokeObjectURL(url);
      if (currentAudio === audio) currentAudio = null;
      if (error) reject(error);
      else resolve();
    };
    audio.onended = () => done();
    audio.onpause = () => done(); // stopVoice() pauses: the reply was interrupted
    audio.onerror = () => done(new Error("audio playback failed"));
    audio.play().catch(done);
  });
}
