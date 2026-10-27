import type { TrackingFrame } from './index';
export const clamp = (n: number) => Math.max(-1, Math.min(1, n)) || 0;
export function pose(matrix: readonly number[], time: number): TrackingFrame | null {
    if (matrix.length !== 16 || !matrix.every(Number.isFinite) || !Number.isFinite(time))
        return null;
    // Reject degenerate/extreme bases, not translation (which is in model units).
    for (const i of [0, 4, 8]) {
        const norm = Math.hypot(matrix[i]!, matrix[i + 1]!, matrix[i + 2]!);
        if (norm < 0.5 || norm > 2)
            return null;
    }
    for (const [i, j] of [[0, 4], [0, 8], [4, 8]] as const) {
        const dot = matrix[i]! * matrix[j]! + matrix[i + 1]! * matrix[j + 1]! + matrix[i + 2]! * matrix[j + 2]!;
        if (Math.abs(dot) > 0.25 * Math.hypot(matrix[i]!, matrix[i + 1]!, matrix[i + 2]!) * Math.hypot(matrix[j]!, matrix[j + 1]!, matrix[j + 2]!))
            return null;
    }
    const det = matrix[0]! * (matrix[5]! * matrix[10]! - matrix[9]! * matrix[6]!) - matrix[4]! * (matrix[1]! * matrix[10]! - matrix[9]! * matrix[2]!) + matrix[8]! * (matrix[1]! * matrix[6]! - matrix[5]! * matrix[2]!);
    if (det < 0.1 || det > 8)
        return null;
    // MediaPipe column-major canonical-face rotation matrix. Approximate head aim.
    const yaw = clamp(Math.atan2(matrix[8]!, matrix[10]!) / (Math.PI / 3));
    const pitch = clamp(Math.atan2(-matrix[9]!, Math.hypot(matrix[8]!, matrix[10]!)) / (Math.PI / 4));
    const roll = clamp(Math.atan2(matrix[1]!, matrix[0]!) / (Math.PI / 4));
    return { yaw, pitch, roll, gazeX: yaw, gazeY: pitch, confidence: 1, timestamp: time };
}
