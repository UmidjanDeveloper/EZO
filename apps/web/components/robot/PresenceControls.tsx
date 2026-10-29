"use client";
import { Camera, CameraOff } from "lucide-react";
import { useI18n } from "@/lib/i18n/context";
import { storedCaptions, storedIntensity, storedMotion, storedQuality } from "@/lib/presence/preferences";
import type { useFaceAttention } from "@/lib/presence/use-face-attention";
import { setVoiceVolume, storedVoiceRate, storedVoiceVolume } from "@/lib/voice/engine";

/** The same accessible controls in the voice drawer and device settings. */
export function PresenceControls({ camera, voice = false }: { camera?: ReturnType<typeof useFaceAttention>; voice?: boolean }) {
  const { m } = useI18n();
  const t = m.energy;
  const quality = storedQuality.useValue();
  const motion = storedMotion.useValue();
  const intensity = storedIntensity.useValue();
  const captions = storedCaptions.useValue();
  const rate = storedVoiceRate.useValue();
  const volume = storedVoiceVolume.useValue();
  const field = "min-h-11 w-full rounded-lg border border-slate-600 bg-slate-950 px-3 text-sm text-slate-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cyan-300";
  const cameraWords = { off: t.cameraOff, requesting: t.cameraRequesting, loading: t.cameraLoading, searching: t.cameraSearching, tracking: t.cameraTracking, error: t.cameraOff };
  const cameraError = camera?.error === "denied" ? t.cameraDenied : camera?.error === "tracking" ? t.cameraTrackingError : t.cameraUnavailable;
  return (
    <div className="flex flex-col gap-4 rounded-xl bg-black/80 p-4 text-sm text-slate-200" data-testid="presence-controls">
      <label className="flex flex-col gap-2">{t.quality}
        <select className={field} value={quality} onChange={(event) => storedQuality.set(event.target.value as typeof quality)} data-testid="quality-profile">
          <option value="auto">{t.auto}</option><option value="high">{t.high}</option><option value="balanced">{t.balanced}</option><option value="low">{t.low}</option>
        </select>
      </label>
      <label className="flex min-h-11 cursor-pointer items-center gap-3">
        <input type="checkbox" className="h-5 w-5 accent-cyan-300" checked={motion === "reduced"} onChange={(event) => storedMotion.set(event.target.checked ? "reduced" : "system")} data-testid="reduce-motion" />
        {t.motion}
      </label>
      <label className="flex flex-col gap-2">{t.intensity}
        <input type="range" min="0" max="1" step="0.05" value={intensity} onChange={(event) => storedIntensity.set(event.target.value)} className="min-h-8 accent-cyan-300" data-testid="light-intensity" />
      </label>
      {voice ? <>
        <label className="flex min-h-11 cursor-pointer items-center gap-3">
          <input type="checkbox" className="h-5 w-5 accent-cyan-300" checked={captions === "on"} onChange={(event) => storedCaptions.set(event.target.checked ? "on" : "off")} data-testid="voice-captions-toggle" />{t.captions}
        </label>
        <label className="flex flex-col gap-2">{m.voice.volume}
          <input type="range" min="0" max="1" step="0.05" value={volume} onChange={(event) => setVoiceVolume(Number(event.target.value))} className="min-h-8 accent-cyan-300" data-testid="voice-volume" />
        </label>
        <label className="flex flex-col gap-2">{t.rate}
          <input type="range" min="0.7" max="1.3" step="0.1" value={rate} onChange={(event) => storedVoiceRate.set(event.target.value)} className="min-h-8 accent-cyan-300" data-testid="voice-rate" />
          <span className="text-xs text-slate-400">{Number(rate).toFixed(1)}× · {m.settings.voiceBrowser}</span>
        </label>
      </> : null}
      {camera ? <section className="flex flex-col gap-2 border-t border-slate-700 pt-4" aria-label={t.camera}>
        <button type="button" onClick={() => camera.active ? camera.stop() : void camera.start()} aria-pressed={camera.active}
          className="flex min-h-11 items-center justify-center gap-2 rounded-lg border border-cyan-300/40 px-3 text-cyan-100 hover:bg-cyan-300/10 focus-visible:outline-2 focus-visible:outline-cyan-300" data-testid="camera-toggle">
          {camera.active ? <CameraOff size={16} /> : <Camera size={16} />}{camera.active ? t.stopCamera : t.enableCamera}
        </button>
        <p role="status" className="text-xs text-cyan-100" data-testid="camera-status" data-status={camera.status}>{cameraWords[camera.status]}</p>
        {camera.error ? <p role="alert" className="text-xs text-amber-200">{cameraError}</p> : null}
        <p className="text-xs leading-relaxed text-slate-400">{t.cameraHint}</p>
      </section> : null}
    </div>
  );
}
