"use client";

import { Button, Card, cn, Spinner, TextAreaField } from "@ezo/ui";
import {
  Award,
  ChevronRight,
  Mic,
  MicOff,
  RotateCcw,
  Send,
  Square,
  Volume2,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { apiUrl, storedToken } from "@/lib/api";
import { useI18n } from "@/lib/i18n/context";
import type { VoiceStatus as ServerVoice } from "@ezo/shared";
import { api } from "@/lib/api";
import {
  listenOnce,
  speak,
  speechRecognitionSupported,
  speechSynthesisSupported,
} from "@/lib/speech";
import {
  LONG_ANSWER_VAD,
  listenWithServer,
  pickListener,
  serverRecordingSupported,
  speakReply,
} from "@/lib/voice/engine";
import { PageFrame } from "./PageFrame";

interface CueCard {
  id: string;
  task: string;
  points: string[];
  follow_up: string;
  discussion: string[];
}

interface VoiceStatus {
  available: boolean;
  provider: string;
  fallback_mode: string;
  notice_uz: string;
  notice_en: string;
}

interface IeltsSession {
  id: string;
  status: string;
  ielts_part: number;
  cue_card: string | null;
  current_prompt: string | null;
  answered_count: number;
  finished: boolean;
  band_low: number | null;
  band_high: number | null;
  feedback: string | null;
}

interface IeltsStats {
  total_sessions: number;
  completed_sessions: number;
  average_band: number | null;
  best_band: number | null;
  total_speaking_minutes: number;
  common_mistakes: string[];
}

interface EvaluationResult {
  fluency_score: number | null;
  lexical_score: number | null;
  grammar_score: number | null;
  pronunciation_score: number | null;
  estimated_band_low: number | null;
  estimated_band_high: number | null;
  estimated_band: number | null;
  constructive_feedback: string;
  explanation_uz: string;
  disclaimer: string;
}

export function IeltsPage() {
  const { m, f } = useI18n();

  const [cueCards, setCueCards] = useState<CueCard[]>([]);
  const [selectedCard, setSelectedCard] = useState<CueCard | null>(null);
  const [voiceStatus, setVoiceStatus] = useState<VoiceStatus | null>(null);
  const [stats, setStats] = useState<IeltsStats | null>(null);

  // Active session state
  const [session, setSession] = useState<IeltsSession | null>(null);
  const [answer, setAnswer] = useState("");
  const [loading, setLoading] = useState(false);
  const [evalResult, setEvalResult] = useState<EvaluationResult | null>(null);
  const [stepFeedback, setStepFeedback] = useState<{ feedback: string; uz: string } | null>(null);

  // Real voice and audio interaction
  const [isListening, setIsListening] = useState(false);
  const [stopListeningFn, setStopListeningFn] = useState<(() => void) | null>(null);
  // Seconds measured by the speech recognizer for the current answer; typed answers have none.
  const [speechSeconds, setSpeechSeconds] = useState<number | null>(null);
  const [speakingPrompt, setSpeakingPrompt] = useState(false);

  // Server speech recognition (OpenAI/ElevenLabs/VoiceStudio) when the server has it,
  // otherwise the browser recogniser. Nothing is faked: unsupported paths say so.
  const [serverVoice, setServerVoice] = useState<ServerVoice | null>(null);
  const [serverFailed, setServerFailed] = useState(false);
  const [voiceNote, setVoiceNote] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    api
      .voiceStatus()
      .then((status) => alive && setServerVoice(status))
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, []);

  function toggleListening() {
    if (isListening && stopListeningFn) {
      stopListeningFn();
      setIsListening(false);
      setStopListeningFn(null);
      return;
    }
    const engine = serverRecordingSupported() || speechRecognitionSupported() ? pickListener(serverVoice, serverFailed) : null;
    if (!engine) {
      setVoiceNote(m.ielts.voiceUnsupported);
      return;
    }
    setVoiceNote(null);
    setIsListening(true);
    const handlers = {
      onInterim: (text: string) => setAnswer(text),
      onFinal: (text: string, info?: { speechSeconds?: number | null }) => {
        setAnswer(text);
        // Measured from the recording on this device; the API labels it client-reported.
        if (info?.speechSeconds) setSpeechSeconds(info.speechSeconds);
      },
      onEnd: (error: string | null) => {
        setIsListening(false);
        setStopListeningFn(null);
        if (error === "server-failed") setServerFailed(true);
        if (error === "not-allowed") setVoiceNote(m.ielts.micDenied);
        else if (error === "no-speech") setVoiceNote(m.ielts.noSpeech);
      },
    };
    const stop =
      engine === "server" ? listenWithServer("en", handlers, LONG_ANSWER_VAD) : listenOnce("en", handlers);
    setStopListeningFn(() => stop);
  }

  function handleSpeakPrompt(text: string) {
    if (!text) return;
    if (!serverVoice?.text_to_speech.length && !speechSynthesisSupported()) return;
    setSpeakingPrompt(true);
    // The examiner question in a real voice when the server has one; browser voice otherwise.
    void (serverVoice ? speakReply(text, "en", serverVoice) : speak(text, "en")).finally(() => setSpeakingPrompt(false));
  }

  const authHeaders = useCallback(() => {
    const token = storedToken.get().trim();
    return {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    };
  }, []);

  const [refreshIndex, setRefreshIndex] = useState(0);
  const refresh = useCallback(() => setRefreshIndex((v) => v + 1), []);

  useEffect(() => {
    let cancelled = false;
    const headers = authHeaders();

    fetch(`${apiUrl()}/api/ielts/cue-cards`, { headers })
      .then((res) => (res.ok ? res.json() : null))
      .then((cards: CueCard[] | null) => {
        if (!cancelled && cards) {
          setCueCards(cards);
          setSelectedCard((current) => current ?? (cards.length > 0 ? cards[0] : null));
        }
      })
      .catch(() => {});

    fetch(`${apiUrl()}/api/ielts/voice-status`, { headers })
      .then((res) => (res.ok ? res.json() : null))
      .then((voice: VoiceStatus | null) => {
        if (!cancelled && voice) setVoiceStatus(voice);
      })
      .catch(() => {});

    fetch(`${apiUrl()}/api/ielts/stats`, { headers })
      .then((res) => (res.ok ? res.json() : null))
      .then((statsData: IeltsStats | null) => {
        if (!cancelled && statsData) setStats(statsData);
      })
      .catch(() => {});

    return () => {
      cancelled = true;
    };
  }, [authHeaders, refreshIndex]);

  async function startNewSession() {
    setLoading(true);
    setStepFeedback(null);
    setEvalResult(null);
    try {
      const res = await fetch(`${apiUrl()}/api/ielts/sessions`, {
        method: "POST",
        headers: authHeaders(),
        // The Part 2 card the learner picked in the bank (F25); otherwise EZO chooses.
        body: JSON.stringify({ target_band: 7.0, cue_card: selectedCard?.id ?? null }),
      });
      if (res.ok) {
        const data = (await res.json()) as IeltsSession;
        setSession(data);
        setAnswer("");
      }
    } finally {
      setLoading(false);
    }
  }

  async function submitAnswer() {
    if (!session || !answer.trim()) return;
    setLoading(true);
    try {
      // 1. Observable practice feedback; absent assessment scores remain null
      const evalRes = await fetch(`${apiUrl()}/api/ielts/evaluate`, {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify({ answer: answer.trim(), part: session.ielts_part }),
      });
      if (evalRes.ok) {
        const ev = (await evalRes.json()) as EvaluationResult;
        setEvalResult(ev);
      }

      // 2. Advance test session
      const advRes = await fetch(`${apiUrl()}/api/ielts/sessions/${session.id}/advance`, {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify({ answer: answer.trim(), speech_seconds: speechSeconds }),
      });
      if (advRes.ok) {
        const adv = await advRes.json();
        setAnswer("");
        setSpeechSeconds(null);
        if (adv.feedback) {
          setStepFeedback({
            feedback: adv.feedback,
            uz: adv.explanation_uz || "",
          });
        }
        // Refresh session
        const sessRes = await fetch(`${apiUrl()}/api/ielts/sessions/${session.id}`, {
          headers: authHeaders(),
        });
        if (sessRes.ok) {
          setSession((await sessRes.json()) as IeltsSession);
        }
        refresh();
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <PageFrame
      title={m.ielts.title}
      subtitle={m.ielts.subtitle}
      actions={
        <Button
          variant="primary"
          size="sm"
          icon={<RotateCcw size={14} />}
          onClick={() => void startNewSession()}
        >
          {m.ielts.startSession}
        </Button>
      }
    >
      {/* Voice / Audio Fallback Indicator Banner */}
      <Card className="mb-6 border-line bg-surface-2/40">
        <div className="flex items-start gap-3">
          <div className="rounded-xl bg-accent2/10 p-2.5 text-accent2">
            <MicOff size={20} />
          </div>
          <div className="flex-1">
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold uppercase tracking-wider text-accent2">
                {m.ielts.voiceOffline}
              </span>
              <span className="rounded-md bg-surface-3 px-2 py-0.5 text-xs text-ink-muted">
                {voiceStatus?.provider ?? "offline_text_fallback"}
              </span>
            </div>
            <p className="mt-1 text-xs leading-relaxed text-ink-muted">
              {voiceStatus?.notice_uz ?? m.ielts.voiceNoticeFallback}
            </p>
          </div>
        </div>
      </Card>

      {/* Preparation Stats Bar */}
      <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div className="rounded-xl border border-line bg-surface p-3.5">
          <p className="text-xs text-ink-muted">{m.ielts.history}</p>
          <p className="mt-1 text-lg font-bold text-ink">{stats?.total_sessions ?? 0}</p>
        </div>
        <div className="rounded-xl border border-line bg-surface p-3.5">
          <p className="text-xs text-ink-muted">{m.ielts.estimatedBand}</p>
          <p className="mt-1 text-lg font-bold text-accent">
            {stats?.average_band ? stats.average_band.toFixed(1) : "—"}
          </p>
        </div>
        <div className="rounded-xl border border-line bg-surface p-3.5">
          <p className="text-xs text-ink-muted">{m.ielts.bestBand}</p>
          <p className="mt-1 text-lg font-bold text-success">
            {stats?.best_band ? stats.best_band.toFixed(1) : "—"}
          </p>
        </div>
        <div className="rounded-xl border border-line bg-surface p-3.5">
          <p className="text-xs text-ink-muted">{m.ielts.speakingTime}</p>
          <p className="mt-1 text-lg font-bold text-ink">
            {f(m.ielts.minutes, { count: stats?.total_speaking_minutes || 0 })}
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Left Column: Speaking Simulator Workflow (2 cols) */}
        <div className="space-y-6 lg:col-span-2">
          {session ? (
            <Card className="space-y-4 border-accent/30">
              <div className="flex items-center justify-between border-b border-line pb-3">
                <div className="flex items-center gap-2">
                  <span className="rounded-full bg-accent px-2.5 py-0.5 text-xs font-semibold text-white">
                    Part {session.ielts_part}
                  </span>
                  <h3 className="text-sm font-semibold text-ink">
                    {session.ielts_part === 1
                      ? m.ielts.part1Title
                      : session.ielts_part === 2
                        ? m.ielts.part2Title
                        : m.ielts.part3Title}
                  </h3>
                </div>
                <span className="text-xs text-ink-muted">
                  {f(m.ielts.answersCount, { count: session.answered_count })}
                </span>
              </div>

              {/* Examiner Prompt */}
              <div className="rounded-xl border border-line bg-surface-2/60 p-4">
                <div className="flex items-center justify-between">
                  <p className="text-xs font-semibold uppercase tracking-wider text-accent">
                    {m.ielts.examinerQuestion}
                  </p>
                  {session.current_prompt && (
                    <button
                      type="button"
                      className="flex items-center gap-1 rounded-md bg-surface-3 px-2 py-0.5 text-xs text-ink-muted hover:text-ink transition-colors"
                      onClick={() => handleSpeakPrompt(session.current_prompt || "")}
                    >
                      <Volume2 size={13} className={speakingPrompt ? "text-accent animate-pulse" : ""} />
                      {speakingPrompt ? m.ielts.reading : m.ielts.listenQuestion}
                    </button>
                  )}
                </div>
                <p className="mt-1.5 whitespace-pre-line text-base font-medium leading-relaxed text-ink">
                  {session.current_prompt || m.ielts.preparingQuestion}
                </p>
              </div>

              {/* Answer submission */}
              {!session.finished ? (
                <div className="space-y-3">
                  <TextAreaField
                    label={m.ielts.yourAnswer}
                    placeholder={m.ielts.answerPlaceholder}
                    value={answer}
                    onChange={(e) => setAnswer(e.target.value)}
                    rows={4}
                  />
                  {stepFeedback ? (
                    <div className="rounded-lg bg-surface-2 p-3 text-xs space-y-1">
                      <p className="font-medium text-ink">{stepFeedback.feedback}</p>
                      {stepFeedback.uz ? <p className="text-accent">{stepFeedback.uz}</p> : null}
                    </div>
                  ) : null}
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <Button
                        type="button"
                        variant={isListening ? "primary" : "secondary"}
                        size="sm"
                        icon={
                          isListening ? (
                            <Square size={13} className="text-red-500 animate-pulse" />
                          ) : (
                            <Mic size={13} />
                          )
                        }
                        onClick={toggleListening}
                      >
                        {isListening ? m.ielts.stopListening : m.ielts.answerByVoice}
                      </Button>
                      <p className="text-xs text-ink-muted">
                        {f(m.ielts.wordCount, { count: answer.split(/\s+/).filter(Boolean).length })}
                        {speechSeconds ? ` · ${f(m.ielts.speechMeasured, { seconds: Math.round(speechSeconds) })}` : ""}
                      </p>
                      {voiceNote ? <p className="text-xs text-red-500">{voiceNote}</p> : null}
                    </div>
                    <Button
                      variant="primary"
                      icon={<Send size={15} />}
                      disabled={loading || !answer.trim()}
                      onClick={() => void submitAnswer()}
                    >
                      {loading ? <Spinner /> : m.ielts.submitAnswer}
                    </Button>
                  </div>
                </div>
              ) : (
                <div className="rounded-xl bg-success/10 p-4 text-center text-success">
                  <Award size={32} className="mx-auto mb-2" />
                  <p className="text-base font-semibold">{m.ielts.finished}</p>
                  <p className="mt-1 text-sm text-ink-muted">
                    {session.band_low != null && session.band_high != null
                      ? f(m.ielts.estimatedResult, { low: session.band_low, high: session.band_high })
                      : m.ielts.noScore}
                  </p>
                </div>
              )}
            </Card>
          ) : (
            <Card className="flex flex-col items-center justify-center p-8 text-center">
              <Award size={48} className="mb-3 text-accent" />
              <h3 className="text-base font-semibold text-ink">{m.ielts.startHeading}</h3>
              <p className="mt-1 max-w-md text-xs text-ink-muted">{m.ielts.startDesc}</p>
              <Button
                variant="primary"
                className="mt-4"
                icon={<Award size={16} />}
                onClick={() => void startNewSession()}
              >
                {m.ielts.startSession}
              </Button>
            </Card>
          )}

          {/* Feedback & Criteria Breakdown */}
          {evalResult ? (
            <Card className="space-y-4 border-line">
              <div className="flex items-center justify-between border-b border-line pb-3">
                <h4 className="text-sm font-semibold text-ink">
                  {m.ielts.feedback}
                </h4>
                <span className="rounded-lg bg-accent/20 px-2.5 py-1 text-sm font-bold text-accent">
                  Band {evalResult.estimated_band?.toFixed(1) ?? "—"}
                </span>
              </div>

              {/* 4 Criteria Grid */}
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                <div className="rounded-lg bg-surface-2 p-2.5 text-center">
                  <p className="text-xs text-ink-muted">{m.ielts.fluency}</p>
                  <p className="text-base font-bold text-ink">
                    {evalResult.fluency_score?.toFixed(1) ?? "—"}
                  </p>
                </div>
                <div className="rounded-lg bg-surface-2 p-2.5 text-center">
                  <p className="text-xs text-ink-muted">{m.ielts.lexical}</p>
                  <p className="text-base font-bold text-ink">
                    {evalResult.lexical_score?.toFixed(1) ?? "—"}
                  </p>
                </div>
                <div className="rounded-lg bg-surface-2 p-2.5 text-center">
                  <p className="text-xs text-ink-muted">{m.ielts.grammar}</p>
                  <p className="text-base font-bold text-ink">
                    {evalResult.grammar_score?.toFixed(1) ?? "—"}
                  </p>
                </div>
                <div className="rounded-lg bg-surface-2 p-2.5 text-center">
                  <p className="text-xs text-ink-muted">{m.ielts.pronunciation}</p>
                  <p className="text-base font-bold text-ink">
                    {evalResult.pronunciation_score?.toFixed(1) ?? "—"}
                  </p>
                </div>
              </div>

              <div className="space-y-2 text-xs leading-relaxed text-ink-muted">
                <p>
                  <strong className="text-ink">{m.ielts.englishFeedback}</strong>{" "}
                  {evalResult.constructive_feedback}
                </p>
                <p className="rounded-lg bg-accent/5 p-3 text-accent">
                  <strong className="text-ink">{m.ielts.uzbekAdviceLabel}</strong>{" "}
                  {evalResult.explanation_uz}
                </p>
              </div>

              <p className="text-[11px] italic text-ink-faint">
                {evalResult.disclaimer}
              </p>
            </Card>
          ) : null}
        </div>

        {/* Right Column: Cue Cards Bank (1 col) */}
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-ink">
              {m.ielts.cueCard}
            </h3>
            <span className="text-xs text-ink-muted">{f(m.ielts.cardCount, { count: cueCards.length })}</span>
          </div>

          <div className="space-y-3">
            {cueCards.map((card) => {
              const active = selectedCard?.id === card.id;
              return (
                <div
                  key={card.id}
                  onClick={() => setSelectedCard(card)}
                  className={cn(
                    "cursor-pointer rounded-xl border p-3.5 transition-all",
                    active
                      ? "border-accent bg-accent/5 shadow-sm"
                      : "border-line bg-surface hover:border-accent/40",
                  )}
                >
                  <p className="text-sm font-semibold text-ink">{card.task}</p>
                  <ul className="mt-2 space-y-1 text-xs text-ink-muted">
                    {card.points.map((pt, i) => (
                      <li key={i} className="flex items-center gap-1.5">
                        <ChevronRight size={12} className="text-accent" />
                        <span>{pt}</span>
                      </li>
                    ))}
                  </ul>
                  <div className="mt-3 border-t border-line/60 pt-2 text-[11px] text-ink-faint">
                    {m.ielts.followUp} {card.follow_up}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </PageFrame>
  );
}
