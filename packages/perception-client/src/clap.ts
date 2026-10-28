import type { ClapDetected } from './types';
export interface ClapOptions {
    sensitivity?: number;
    cooldownMs?: number;
}
/** Bounded 10ms PCM windows; heuristic transient detector, NOT general sound classification. */
export class ClapDetector {
    private noise = 0.005;
    private previousRms = 0;
    private candidate: {
        at: number;
        peak: number;
        confidence: number;
    } | null = null;
    private last = -Infinity;
    private lastEvent = -Infinity;
    private samples = 0;
    private energy = 0;
    private peak = 0;
    private crossings = 0;
    private previousSample = 0;
    private readonly sensitivity: number;
    private readonly cooldown: number;
    constructor(private readonly options: ClapOptions = {}) {
        this.sensitivity = options.sensitivity ?? 1;
        this.cooldown = options.cooldownMs ?? 1200;
        if (!Number.isFinite(this.sensitivity) || this.sensitivity < 0.5 || this.sensitivity > 2 || !Number.isFinite(this.cooldown) || this.cooldown < 500 || this.cooldown > 10000)
            throw new Error('Invalid clap sensitivity/cooldown');
    }
    push(samples: Float32Array, sampleRate: number, startMs: number): ClapDetected[] {
        if (!Number.isFinite(sampleRate) || sampleRate < 8000 || sampleRate > 192000 || !Number.isFinite(startMs) || startMs <= this.last || samples.length > sampleRate)
            return [];
        if (this.last !== -Infinity && startMs - this.last > 100) {
            this.candidate = null;
            this.previousRms = 0;
            this.samples = 0;
            this.energy = 0;
            this.peak = 0;
            this.crossings = 0;
        }
        const events: ClapDetected[] = [];
        const size = Math.round(sampleRate / 100);
        for (let i = 0; i < samples.length; i++) {
            const v = samples[i]!;
            if (!Number.isFinite(v) || Math.abs(v) > 1) {
                this.reset();
                return [];
            }
            this.energy += v * v;
            this.peak = Math.max(this.peak, Math.abs(v));
            if (v * this.previousSample < 0)
                this.crossings++;
            this.previousSample = v;
            this.samples++;
            if (this.samples >= size) {
                const time = startMs + i * 1000 / sampleRate, rms = Math.sqrt(this.energy / this.samples), zcr = this.crossings / this.samples;
                const candidate = this.candidate;
                if (candidate) {
                    if (time - candidate.at > 100)
                        this.candidate = null;
                    else if (time - candidate.at >= 10 && rms < candidate.peak * 0.25) {
                        this.lastEvent = time;
                        events.push({ type: 'clap_detected', timestampMs: time, confidence: candidate.confidence, evidence: 'acoustic_transient', authorization: 'acknowledgement_only' });
                        this.candidate = null;
                    }
                }
                else if (time - this.lastEvent >= this.cooldown && rms > 0.10 / this.sensitivity && rms > this.noise * 7 / this.sensitivity && rms > Math.max(0.015, this.previousRms) * 3 && this.peak > 0.35 && zcr > 0.12) {
                    this.candidate = { at: time, peak: rms, confidence: Math.min(0.95, 0.7 + zcr * 0.3) };
                }
                if (!this.candidate)
                    this.noise = 0.98 * this.noise + 0.02 * Math.min(0.08, rms);
                this.previousRms = rms;
                this.samples = 0;
                this.energy = 0;
                this.peak = 0;
                this.crossings = 0;
            }
        }
        this.last = startMs + samples.length * 1000 / sampleRate - 0.001;
        return events;
    }
    reset() { this.noise = 0.005; this.previousRms = 0; this.candidate = null; this.last = -Infinity; this.lastEvent = -Infinity; this.samples = 0; this.energy = 0; this.peak = 0; this.crossings = 0; this.previousSample = 0; }
}
