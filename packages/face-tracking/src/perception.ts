import { CameraTracker } from './index';
import { AttentionController } from './attention';
import { ClapMicrophone } from './microphone';
import { createVisionEstimator } from './vision';
import type { VisionAssets } from './vision';
import type { TrackingStatus } from './index';
import type { MicrophoneStatus } from './microphone';
import type { ClapDetected, HandTarget, MotionIntent, PerceptionFrame } from './types';
export interface PerceptionOptions {
    video: HTMLVideoElement;
    cameraIndicator: HTMLElement;
    microphoneIndicator: HTMLElement;
    assets: VisionAssets;
    mirrored?: boolean;
    reducedMotion?: boolean;
    lowPower?: boolean;
    onMotionIntent: (intent: MotionIntent) => void;
    onHandMovement?: (hands: readonly HandTarget[]) => void;
    onClapDetected?: (event: ClapDetected) => void;
    onStatus?: (sensor: 'camera' | 'microphone', status: TrackingStatus | MicrophoneStatus) => void;
    onError?: (sensor: 'camera' | 'microphone', message: string) => void;
    /** Confirmed Permissions API denied transition when supported. Track interruptions go to onError. */
    onPermissionRevoked?: (sensor: 'camera' | 'microphone') => void;
    onMetrics?: (metrics: {
        inferenceMs: number;
        sampleTimestampMs: number;
    }) => void;
}
/** Single sensing owner, reuses CameraTracker. No permission requests in constructor. */
export class HumanoidPerception {
    readonly attention: AttentionController;
    private readonly camera: CameraTracker;
    private readonly microphone: ClapMicrophone;
    private render: number | undefined;
    private status: TrackingStatus = 'off';
    private active = false;
    private readonly pagehide = () => this.stop();
    private readonly hide = () => { if (document.hidden)
        this.stop(); };
    constructor(private readonly options: PerceptionOptions) {
        this.attention = new AttentionController({ mirrored: options.mirrored, reducedMotion: options.reducedMotion });
        const error = (sensor: 'camera' | 'microphone', message?: string) => { if (!message)
            return; options.onError?.(sensor, message); if (message.includes('revoked'))
            options.onPermissionRevoked?.(sensor); };
        this.microphone = new ClapMicrophone({ indicator: options.microphoneIndicator, onClap: event => options.onClapDetected?.(event), onStatus: (s, e) => { options.onStatus?.('microphone', s); error('microphone', e); } });
        this.camera = new CameraTracker({ video: options.video, indicator: options.cameraIndicator, lowPower: options.lowPower,
            createEstimator: (signal) => createVisionEstimator(options.assets, frame => this.frame(frame), { signal }), onFrame: () => { },
            onStatus: (s, e) => { this.status = s; options.onStatus?.('camera', s); error('camera', e); if (s === 'error') {
                this.stopRender();
                this.attention.reset();
                options.onMotionIntent(this.attention.sample(performance.now()));
            } }
        });
    }
    private frame(frame: PerceptionFrame) { if (!this.active)
        return; const now = performance.now(); if (!this.attention.ingest(frame, now))
        return; this.microphone.detector.observeHands(frame.handsDistance, now); this.options.onHandMovement?.(frame.hands); this.options.onMetrics?.({ inferenceMs: frame.inferenceMs, sampleTimestampMs: frame.timestampMs }); }
    get trackingStatus() { return this.status; }
    get currentAttentionTarget() { return this.attention.sample(performance.now()); }
    /** These methods ARE permission actions: bind each to a separate visible button. */
    async startTracking() { if (document.hidden)
        return; this.active = true; document.addEventListener('visibilitychange', this.hide); globalThis.addEventListener('pagehide', this.pagehide); await this.camera.start(); if (this.active && this.status !== 'error' && this.render === undefined)
        this.tick(); }
    setInteraction(mode: 'listening' | 'speaking' | null) { this.attention.setInteraction(mode); this.microphone.setSuppressed(mode === 'speaking'); }
    async startClapDetection() { await this.microphone.start(); }
    stopClapDetection() { this.microphone.stop(); }
    private tick = () => { if (!this.active)
        return; this.options.onMotionIntent(this.attention.sample(performance.now())); this.render = requestAnimationFrame(this.tick); };
    private stopRender() { if (this.render !== undefined)
        cancelAnimationFrame(this.render); this.render = undefined; }
    stopTracking() { this.active = false; this.camera.stop(); this.stopRender(); this.attention.reset(); this.options.onMotionIntent(this.attention.sample(performance.now())); document.removeEventListener('visibilitychange', this.hide); globalThis.removeEventListener('pagehide', this.pagehide); }
    /** Hidden/disabled view stops BOTH sensors; showing never silently restarts them. */
    setVisible(visible: boolean) { this.camera.setVisible(visible); if (!visible)
        this.stop(); }
    stop() { this.stopTracking(); this.stopClapDetection(); }
}
