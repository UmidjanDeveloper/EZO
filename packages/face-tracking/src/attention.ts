import { clamp } from './pose';
import type { AttentionState, MotionIntent, PerceptionFrame, Target } from './types';
const finiteTarget = (t: Target) => Number.isFinite(t.x) && Number.isFinite(t.y) && Number.isFinite(t.confidence) && Math.abs(t.x) <= 1 && Math.abs(t.y) <= 1 && t.confidence <= 1;
/** Deterministic attention arbitration. Render tick is independent of inference cadence. */
export class AttentionController {
    private frame: PerceptionFrame | null = null;
    private lastTime = -Infinity;
    private hand: Target | null = null;
    private handAt = -Infinity;
    private candidateAt = -Infinity;
    private candidateId = '';
    private mode: 'listening' | 'speaking' | null = null;
    private output: MotionIntent = { source: 'neutral', yaw: 0, pitch: 0, roll: 0, confidence: 0, timestampMs: 0, state: 'neutral' };
    constructor(private readonly options: {
        mirrored?: boolean;
        reducedMotion?: boolean;
        maxAgeMs?: number;
    } = {}) { }
    setInteraction(mode: 'listening' | 'speaking' | null) { this.mode = mode; }
    ingest(frame: PerceptionFrame, now = frame.timestampMs): boolean {
        if (!Number.isFinite(now) || !Number.isFinite(frame.timestampMs) || frame.timestampMs <= this.lastTime || frame.timestampMs > now || now - frame.timestampMs > (this.options.maxAgeMs ?? 500))
            return false;
        this.lastTime = frame.timestampMs;
        const face = frame.face;
        const validFace = face && Object.values(face).every(Number.isFinite) && face.confidence >= 0.6 && face.confidence <= 1 && ['yaw', 'pitch', 'roll', 'gazeX', 'gazeY'].every(k => Math.abs(face[k as keyof typeof face]) <= 1) ? face : null;
        this.frame = { ...frame, face: validFace, hands: frame.hands.filter(h => finiteTarget(h) && h.confidence >= 0.6 && Number.isFinite(h.velocityX) && Number.isFinite(h.velocityY)) };
        const moving = this.frame.hands.find(h => h.moving && Math.hypot(h.velocityX, h.velocityY) > 0.08);
        if (moving) {
            if (this.candidateId !== moving.id || frame.timestampMs - this.candidateAt > 300) {
                this.candidateId = moving.id;
                this.candidateAt = frame.timestampMs;
            }
            // Two observations over >=60ms avoid a single-frame hand stealing focus.
            if (frame.timestampMs - this.candidateAt >= 60) {
                this.hand = moving;
                this.handAt = frame.timestampMs;
            }
        }
        else {
            this.candidateId = '';
            this.candidateAt = -Infinity;
        }
        return true;
    }
    sample(now: number): MotionIntent {
        if (!Number.isFinite(now) || now < this.output.timestampMs)
            return this.output;
        const fresh = this.frame && now - this.frame.timestampMs <= (this.options.maxAgeMs ?? 500);
        const face = fresh ? this.frame!.face : null;
        const hand = fresh && now - this.handAt < 700 ? this.hand : null;
        let source: MotionIntent['source'] = 'neutral', x = 0, y = 0, roll = 0, confidence = 0;
        let state: AttentionState = this.frame ? 'attention_lost' : 'neutral';
        // Explicit mode owns attention; last face target may still direct the head.
        if (hand && !this.mode) {
            source = 'hand';
            x = hand.x;
            y = hand.y;
            confidence = hand.confidence;
            state = 'hand_attention';
        }
        else if (face) {
            source = 'face';
            x = clamp(face.gazeX * 0.75 + face.yaw * 0.25);
            y = clamp(face.gazeY * 0.75 + face.pitch * 0.25);
            roll = face.roll * 0.4;
            confidence = face.confidence;
            state = Math.abs(face.yaw) + Math.abs(face.pitch) > 0.2 ? 'following_head' : 'face_attention';
        }
        if (this.mode)
            state = this.mode;
        const sign = this.options.mirrored ? -1 : 1;
        if (this.options.reducedMotion) {
            x = 0;
            y = 0;
            roll = 0;
        }
        const dt = Math.min(250, Math.max(0, now - this.output.timestampMs));
        // Time-based exponential low pass: ~95% settle in 420ms, independent of render FPS.
        const alpha = 1 - Math.exp(-dt / 140);
        this.output = { source, yaw: clamp(this.output.yaw + alpha * (x * sign - this.output.yaw)), pitch: clamp(this.output.pitch + alpha * (y - this.output.pitch)), roll: clamp(this.output.roll + alpha * (roll * sign - this.output.roll)), confidence, timestampMs: now, state };
        return this.output;
    }
    reset() { this.frame = null; this.lastTime = -Infinity; this.hand = null; this.handAt = -Infinity; this.candidateId = ''; this.candidateAt = -Infinity; this.mode = null; this.output = { source: 'neutral', yaw: 0, pitch: 0, roll: 0, confidence: 0, timestampMs: 0, state: 'neutral' }; }
}
/** Structural port matches the CURRENT @ezo/avatar API. State and voice level remain client-owned. */
export function applyMotion(avatar: {
    setGaze(gaze: {
        yaw: number;
        pitch: number;
    } | null): void;
}, intent: MotionIntent) { avatar.setGaze(intent.source === 'neutral' ? null : { yaw: clamp(intent.yaw), pitch: clamp(intent.pitch) }); }
