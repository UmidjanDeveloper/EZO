"use client";

import type { PronunciationResult } from "@ezo/shared";
import { Button, Card, cn, SelectField, TextAreaField } from "@ezo/ui";
import { Mic, Square } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n/context";
import { pickRecorderType, serverRecordingSupported } from "@/lib/voice/engine";

const LANGS = ["en", "ru", "de", "fr", "es", "tr", "uz"] as const;

const tone: Record<string, string> = {
  ok: "text-success",
  close: "text-warning underline decoration-dotted",
  wrong: "text-danger underline",
  missed: "text-danger line-through",
};

/** Read a sentence aloud; EZO compares what the recognizer heard with what should be said. */
export function PronunciationCard() {
  const { m } = useI18n();
  const t = m.language.pronunciation;
  const [samples, setSamples] = useState<Record<string, string[]>>({});
  const [language, setLanguage] = useState<string>("en");
  const [text, setText] = useState("");
  const [recording, setRecording] = useState(false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<PronunciationResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const recorder = useRef<MediaRecorder | null>(null);

  useEffect(() => {
    void api
      .pronunciationSamples()
      .then((s) => {
        setSamples(s);
        setText((current) => current || s.en?.[0] || "");
      })
      .catch(() => undefined);
  }, []);

  const start = async () => {
    setError(null);
    setResult(null);
    if (!serverRecordingSupported()) {
      setError(t.noMic);
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const type = pickRecorderType((c) => MediaRecorder.isTypeSupported(c));
      const rec = new MediaRecorder(stream, type ? { mimeType: type } : undefined);
      const chunks: Blob[] = [];
      const started = performance.now();
      rec.ondataavailable = (e) => chunks.push(e.data);
      rec.onstop = () => {
        stream.getTracks().forEach((track) => track.stop());
        const blob = new Blob(chunks, { type: rec.mimeType || "audio/webm" });
        const ext = blob.type.includes("mp4") ? "m4a" : blob.type.includes("ogg") ? "ogg" : "webm";
        setBusy(true);
        void api
          .pronunciation(blob, `reading.${ext}`, text, language, performance.now() - started)
          .then(setResult)
          .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
          .finally(() => setBusy(false));
      };
      recorder.current = rec;
      rec.start();
      setRecording(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const stop = () => {
    recorder.current?.stop();
    recorder.current = null;
    setRecording(false);
  };

  const pace = result?.pace ? t[`pace_${result.pace}`] : null;

  return (
    <Card className="p-4" data-testid="pronunciation-card">
      <h2 className="mb-1 text-sm font-medium">{t.title}</h2>
      <p className="mb-3 text-xs text-ink-muted">{t.subtitle}</p>
      <div className="grid gap-3 sm:grid-cols-[10rem_1fr]">
        <SelectField
          label={t.language}
          value={language}
          onChange={(e) => {
            setLanguage(e.target.value);
            setText(samples[e.target.value]?.[0] ?? "");
            setResult(null);
          }}
        >
          {LANGS.map((code) => (
            <option key={code} value={code}>
              {code.toUpperCase()}
            </option>
          ))}
        </SelectField>
        <TextAreaField
          label={t.sentence}
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={2}
          maxLength={600}
          data-testid="pronunciation-text"
        />
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        {recording ? (
          <Button onClick={stop} data-testid="pronunciation-stop">
            <Square size={16} /> {t.stop}
          </Button>
        ) : (
          <Button onClick={() => void start()} disabled={busy || !text.trim()} data-testid="pronunciation-record">
            <Mic size={16} /> {busy ? t.checking : t.record}
          </Button>
        )}
        {samples[language]?.length ? (
          <Button
            variant="ghost"
            onClick={() => {
              const list = samples[language] ?? [];
              setText(list[(list.indexOf(text) + 1) % list.length] ?? "");
              setResult(null);
            }}
          >
            {t.another}
          </Button>
        ) : null}
      </div>
      {error ? <p className="mt-2 text-sm text-danger">{error}</p> : null}
      {result ? (
        <div className="mt-4 flex flex-col gap-2 text-sm" data-testid="pronunciation-result">
          <p>
            <span className="text-2xl font-semibold">{result.score}</span>
            <span className="text-ink-muted"> / 100</span>
            {result.words_per_minute ? (
              <span className="ml-3 text-ink-muted">
                {result.words_per_minute} {t.wpm}
                {pace ? ` · ${pace}` : ""}
              </span>
            ) : null}
          </p>
          <p className="leading-7">
            {result.words.map((w, i) => (
              <span key={i} className={cn("mr-1", tone[w.status])} title={w.heard ? `${t.heard}: ${w.heard}` : undefined}>
                {w.word}
              </span>
            ))}
          </p>
          <p className="text-ink-muted">
            {t.heard}: «{result.heard}»
          </p>
          {result.to_practise.length ? (
            <p>
              {t.practise}: <strong>{result.to_practise.join(", ")}</strong>
            </p>
          ) : (
            <p className="text-success">{t.perfect}</p>
          )}
          <p className="text-xs text-ink-faint">{t.method}</p>
        </div>
      ) : null}
    </Card>
  );
}
