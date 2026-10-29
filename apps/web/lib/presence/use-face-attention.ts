"use client";
import { AttentionFilter, type Gaze } from "@ezo/avatar";
import { useCallback, useEffect, useRef, useState } from "react";

export type CameraStatus = "off" | "requesting" | "loading" | "searching" | "tracking" | "error";
export type CameraError = "denied" | "unavailable" | "tracking" | "insecure";

/** Camera is session-only opt-in. Nothing is persisted, recorded, uploaded or used for identity. */
export function useFaceAttention(onAttention: (gaze: Gaze | null) => void) {
  const [status, setStatus] = useState<CameraStatus>("off");
  const [error, setError] = useState<CameraError | null>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const workerRef = useRef<Worker | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const generationRef = useRef(0);
  const busyRef = useRef(false);
  const callbackRef = useRef(onAttention);
  const filterRef = useRef(new AttentionFilter());
  useEffect(() => { callbackRef.current = onAttention; }, [onAttention]);

  const stop = useCallback(() => {
    generationRef.current++;
    if (timerRef.current) clearInterval(timerRef.current);
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    timerRef.current = null; timeoutRef.current = null;
    workerRef.current?.terminate(); workerRef.current = null;
    streamRef.current?.getTracks().forEach((track) => { track.onended = null; track.stop(); });
    streamRef.current = null;
    if (videoRef.current) { videoRef.current.pause(); videoRef.current.srcObject = null; }
    busyRef.current = false;
    filterRef.current.reset(); callbackRef.current(null);
    setStatus("off"); setError(null);
  }, []);

  const start = useCallback(async () => {
    stop();
    const generation = generationRef.current;
    const alive = () => generation === generationRef.current;
    setError(null);
    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia || typeof Worker === "undefined") {
      setError("unavailable"); setStatus("error"); return;
    }
    setStatus("requesting");
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: false, video: { width: { ideal: 320 }, height: { ideal: 240 }, frameRate: { ideal: 15, max: 15 }, facingMode: "user" } });
    } catch (reason) {
      if (!alive()) return;
      setError(reason instanceof DOMException && ["NotAllowedError", "SecurityError"].includes(reason.name) ? "denied" : "unavailable");
      setStatus("error"); return;
    }
    if (!alive()) { stream.getTracks().forEach((track) => track.stop()); return; }
    streamRef.current = stream;
    stream.getVideoTracks().forEach((track) => { track.onended = () => { if (alive()) { stop(); setError("unavailable"); setStatus("error"); } }; });
    const video = document.createElement("video");
    video.muted = true; video.playsInline = true; video.srcObject = stream;
    videoRef.current = video;
    try { await video.play(); } catch { if (alive()) { stop(); setError("unavailable"); setStatus("error"); } return; }
    if (!alive()) return;
    setStatus("loading");
    let worker: Worker;
    try { worker = new Worker(new URL("./face-worker.ts", import.meta.url), { type: "module" }); }
    catch { stop(); setError("tracking"); setStatus("error"); return; }
    workerRef.current = worker;
    const fail = () => { if (alive()) { stop(); setError("tracking"); setStatus("error"); } };
    timeoutRef.current = setTimeout(fail, 30_000);
    worker.onerror = (event) => { event.preventDefault(); fail(); };
    worker.onmessage = (event: MessageEvent<{ type: string; found?: boolean; yaw?: number; pitch?: number }>) => {
      if (!alive()) return;
      const message = event.data;
      if (message.type === "error") { fail(); return; }
      if (message.type === "ready") {
        if (timeoutRef.current) clearTimeout(timeoutRef.current);
        timeoutRef.current = null;
        setStatus("searching");
        timerRef.current = setInterval(async () => {
          if (busyRef.current || video.readyState < 2 || document.hidden) return;
          busyRef.current = true;
          try {
            const bitmap = await createImageBitmap(video, { resizeWidth: 256, resizeHeight: 192 });
            if (!alive()) { bitmap.close(); return; }
            worker.postMessage({ type: "frame", bitmap, timestamp: performance.now() }, [bitmap]);
          } catch { fail(); }
        }, 100); // bounded 10 Hz inference; rendering stays independent
        return;
      }
      if (message.type === "attention") {
        busyRef.current = false;
        const gaze = filterRef.current.update(message.found ? { yaw: message.yaw ?? 0, pitch: message.pitch ?? 0 } : null, performance.now() / 1000);
        callbackRef.current(gaze);
        setStatus(gaze ? "tracking" : "searching");
      }
    };
    worker.postMessage({ type: "init" });
  }, [stop]);

  useEffect(() => {
    const hidden = () => { if (document.hidden) stop(); };
    document.addEventListener("visibilitychange", hidden);
    window.addEventListener("pagehide", stop);
    return () => { document.removeEventListener("visibilitychange", hidden); window.removeEventListener("pagehide", stop); stop(); };
  }, [stop]);
  return { status, error, start, stop, active: ["requesting", "loading", "searching", "tracking"].includes(status) };
}
