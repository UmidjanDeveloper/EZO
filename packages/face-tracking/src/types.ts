import type { TrackingFrame } from './index';
/** Monotonic performance.now() milliseconds. Never wall-clock/biometric identity. */
export interface Target {
    x: number;
    y: number;
    confidence: number;
}
export interface HandTarget extends Target {
    id: 'left' | 'right' | 'unknown';
    velocityX: number;
    velocityY: number;
    moving: boolean;
}
export interface PerceptionFrame {
    face: TrackingFrame | null;
    hands: HandTarget[];
    timestampMs: number;
    inferenceMs: number;
    handsDistance?: number;
}
export type AttentionState = 'neutral' | 'face_attention' | 'hand_attention' | 'following_head' | 'listening' | 'speaking' | 'attention_lost';
export interface MotionIntent {
    source: 'face' | 'hand' | 'eye' | 'neutral';
    yaw: number;
    pitch: number;
    roll: number;
    confidence: number;
    timestampMs: number;
    state: AttentionState;
}
export interface ClapDetected {
    type: 'clap_detected';
    timestampMs: number;
    confidence: number;
    evidence: 'acoustic_transient' | 'audio_and_hands'; /** Heuristic, not a calibrated probability or command authorization. */
    authorization: 'acknowledgement_only';
}
export type Language = 'uz' | 'en' | 'ru';
export type PlaybackEvent = {
    type: 'start';
    timestampMs: number;
} | {
    type: 'level';
    level: number;
    timestampMs: number;
} | {
    type: 'end' | 'unavailable' | 'error';
    timestampMs: number;
};
