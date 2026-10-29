/**
 * Browser speech: recognition (microphone → text) and synthesis (text → voice).
 *
 * Uses the Web Speech API built into Chrome, Edge and Safari. Firefox has no
 * speech recognition; callers must check `speechRecognitionSupported()`.
 * Server-side realtime voice providers replace this in ROADMAP Phase 8 (realtime voice).
 */

import type { LanguageCode } from "@ezo/shared";

/* Minimal typings: the Web Speech API is not in every TypeScript DOM lib. */
interface RecognitionAlternative {
  transcript: string;
}
interface RecognitionResult {
  readonly isFinal: boolean;
  readonly length: number;
  [index: number]: RecognitionAlternative;
}
interface RecognitionEvent {
  readonly resultIndex: number;
  readonly results: { readonly length: number; [index: number]: RecognitionResult };
}
interface RecognitionErrorEvent {
  readonly error: string;
}
export interface SpeechRecognitionLike {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onresult: ((event: RecognitionEvent) => void) | null;
  onerror: ((event: RecognitionErrorEvent) => void) | null;
  onend: (() => void) | null;
  start(): void;
  stop(): void;
  abort(): void;
}
type RecognitionConstructor = new () => SpeechRecognitionLike;

declare global {
  interface Window {
    SpeechRecognition?: RecognitionConstructor;
    webkitSpeechRecognition?: RecognitionConstructor;
  }
}

export const SPEECH_LOCALES: Record<LanguageCode, string> = {
  uz: "uz-UZ",
  en: "en-US",
  ru: "ru-RU",
};

function recognitionConstructor(): RecognitionConstructor | null {
  if (typeof window === "undefined") return null;
  return window.SpeechRecognition ?? window.webkitSpeechRecognition ?? null;
}

export function speechRecognitionSupported(): boolean {
  return recognitionConstructor() !== null;
}

export function speechSynthesisSupported(): boolean {
  return typeof window !== "undefined" && "speechSynthesis" in window;
}

export interface ListenHandlers {
  onInterim: (text: string) => void;
  /** The recording ended and the words are being recognised (server listener only). */
  onRecognizing?: () => void;
  /** `speechSeconds` is the measured speaking time when the listener can measure it. */
  onFinal: (text: string, info?: { speechSeconds?: number | null; language?: LanguageCode | null }) => void;
  /** Called once when listening stops for any reason (after onFinal, if any). */
  onEnd: (error: string | null) => void;
}

/** Listen for one utterance. Returns a function that stops listening. */
export function listenOnce(language: LanguageCode, handlers: ListenHandlers): () => void {
  const Recognition = recognitionConstructor();
  if (!Recognition) {
    handlers.onEnd("not-supported");
    return () => undefined;
  }
  const recognition = new Recognition();
  recognition.lang = SPEECH_LOCALES[language];
  recognition.continuous = false;
  recognition.interimResults = true;

  let finalText = "";
  let error: string | null = null;
  let ended = false;

  recognition.onresult = (event) => {
    let interim = "";
    for (let i = event.resultIndex; i < event.results.length; i += 1) {
      const result = event.results[i];
      if (!result || result.length === 0) continue;
      const transcript = result[0]?.transcript ?? "";
      if (result.isFinal) finalText += transcript;
      else interim += transcript;
    }
    handlers.onInterim((finalText + interim).trim());
  };
  recognition.onerror = (event) => {
    // "no-speech" and "aborted" are normal (silence / user stopped).
    error = event.error;
  };
  recognition.onend = () => {
    if (ended) return;
    ended = true;
    const text = finalText.trim();
    if (text) handlers.onFinal(text);
    handlers.onEnd(text ? null : error);
  };

  try {
    recognition.start();
  } catch {
    handlers.onEnd("start-failed");
  }
  return () => recognition.stop();
}

/** Turn Markdown into plain sentences that sound natural when read aloud. */
export function toSpeakableText(markdown: string): string {
  return markdown
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/`([^`]*)`/g, "$1")
    .replace(/!\[[^\]]*\]\([^)]*\)/g, " ")
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
    .replace(/https?:\/\/\S+/g, " ")
    .replace(/^\s{0,3}#{1,6}\s+/gm, "")
    .replace(/^\s*[-*+]\s+/gm, "")
    .replace(/^\s*\d+[.)]\s+/gm, "")
    .replace(/^\s*>\s?/gm, "")
    .replace(/\|/g, " ")
    .replace(/[*~]+/g, "")
    // Underscore emphasis (_word_, __word__) but not names like ANTHROPIC_API_KEY.
    .replace(/(^|[\s(])_{1,2}(?=\S)/g, "$1")
    .replace(/(\S)_{1,2}(?=[\s).,!?:;]|$)/g, "$1")
    .replace(/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/gu, "")
    .replace(/\s+/g, " ")
    .trim();
}

function pickVoice(locale: string): SpeechSynthesisVoice | null {
  const voices = window.speechSynthesis.getVoices();
  const prefix = locale.slice(0, 2).toLowerCase();
  return (
    voices.find((voice) => voice.lang.toLowerCase() === locale.toLowerCase()) ??
    voices.find((voice) => voice.lang.toLowerCase().startsWith(prefix)) ??
    null
  );
}

/** True when the device has a voice for the language (otherwise a default voice is used). */
export function hasVoiceFor(language: LanguageCode): boolean {
  if (!speechSynthesisSupported()) return false;
  return pickVoice(SPEECH_LOCALES[language]) !== null;
}

export interface BrowserSpeechOptions {
  volume?: number;
  rate?: number;
  onStart?: () => void;
}
let finishCurrent: (() => void) | null = null;

/** Browser TTS exposes lifecycle events, but no PCM tap. Callers must not pretend otherwise. */
export function speak(text: string, language: LanguageCode, options: BrowserSpeechOptions = {}): Promise<void> {
  stopSpeaking();
  return new Promise((resolve) => {
    if (!speechSynthesisSupported() || !text.trim()) { resolve(); return; }
    const synthesis = window.speechSynthesis;
    const utterance = new SpeechSynthesisUtterance(text);
    const locale = SPEECH_LOCALES[language];
    utterance.lang = locale;
    const voice = pickVoice(locale);
    if (voice) utterance.voice = voice;
    utterance.rate = Math.max(0.7, Math.min(1.3, options.rate ?? 1));
    utterance.volume = Math.max(0, Math.min(1, options.volume ?? 1));
    let finished = false;
    const finish = () => {
      if (finished) return;
      finished = true;
      if (finishCurrent === finish) finishCurrent = null;
      resolve();
    };
    finishCurrent = finish;
    utterance.onstart = () => { if (!finished) options.onStart?.(); };
    utterance.onend = finish;
    utterance.onerror = finish;
    try { synthesis.speak(utterance); } catch { finish(); }
  });
}

export function stopSpeaking(): void {
  if (speechSynthesisSupported()) window.speechSynthesis.cancel();
  finishCurrent?.();
}
