import { clamp, pose } from './pose';
import type { TrackingFrame } from './index';
import type { HandTarget } from './types';
export interface Landmark {
    x: number;
    y: number;
}
export function faceFrame(landmarks: Landmark[][], matrices: {
    data: number[];
}[], time: number): TrackingFrame | null {
    if (landmarks.length !== 1)
        return null;
    const tracked = pose(matrices[0]?.data ?? [], time), nose = landmarks[0]?.[1];
    if (!tracked || !nose || !Number.isFinite(nose.x) || !Number.isFinite(nose.y) || nose.x < 0 || nose.x > 1 || nose.y < 0 || nose.y > 1)
        return null;
    // SDK doesn't expose pose probability. 0.8 is a conservative accepted-quality label, NOT accuracy.
    return { ...tracked, gazeX: clamp(nose.x * 2 - 1), gazeY: clamp(1 - nose.y * 2), confidence: 0.8 };
}
/** Handedness is only a transient association hint; no person/hand biometric identity. */
export class HandMotionTracker {
    private prior = new Map<string, {
        x: number;
        y: number;
        time: number;
        moving: boolean;
    }>();
    private last = -Infinity;
    update(landmarks: Landmark[][], handedness: {
        categoryName: string;
        score: number;
    }[][], time: number): HandTarget[] {
        if (!Number.isFinite(time) || time <= this.last)
            return [];
        this.last = time;
        const next = new Map<string, {
            x: number;
            y: number;
            time: number;
            moving: boolean;
        }>(), hands: HandTarget[] = [];
        for (let i = 0; i < Math.min(2, landmarks.length); i++) {
            const points = landmarks[i], category = handedness[i]?.[0];
            if (!points || points.length !== 21 || !category || !Number.isFinite(category.score) || category.score < 0.6 || category.score > 1)
                continue;
            const palm = [0, 5, 9, 13, 17].map(i => points[i]!);
            if (palm.some(p => !Number.isFinite(p.x) || !Number.isFinite(p.y) || p.x < 0 || p.x > 1 || p.y < 0 || p.y > 1))
                continue;
            const x = clamp(palm.reduce((n, p) => n + p.x, 0) / palm.length * 2 - 1), y = clamp(1 - palm.reduce((n, p) => n + p.y, 0) / palm.length * 2);
            const id = category.categoryName === 'Left' ? 'left' : category.categoryName === 'Right' ? 'right' : 'unknown';
            const old = this.prior.get(id), dt = old ? (time - old.time) / 1000 : 0;
            const velocityX = old && dt > 0 && dt < 0.5 ? (x - old.x) / dt : 0, velocityY = old && dt > 0 && dt < 0.5 ? (y - old.y) / dt : 0;
            const moving = Math.hypot(velocityX, velocityY) > (old?.moving ? 0.04 : 0.08);
            hands.push({ x, y, id, confidence: Math.min(0.8, category.score), velocityX, velocityY, moving });
            next.set(id, { x, y, time, moving });
        }
        this.prior = next;
        return hands;
    }
    reset() { this.prior.clear(); this.last = -Infinity; }
}
