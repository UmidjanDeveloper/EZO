import { afterEach, describe, expect, it, vi } from 'vitest';
import { createVisionEstimator, MEDIAPIPE_ASSET_PINS } from './index';
import type { VisionAssets } from './index';

// Deadlines are a scheduling budget, not hardware validation: a worker that never answers
// is terminated at the budget, and the budget for initialization is separate from frames.
const assets: VisionAssets = {
    face: { url: '/vision/face.task', sha256: 'a'.repeat(64) },
    hand: { url: '/vision/hand.task', sha256: 'b'.repeat(64) },
    wasmLoader: { url: '/vision/loader.js', sha256: MEDIAPIPE_ASSET_PINS.loaderSha256 },
    wasmBinary: { url: '/vision/binary.wasm', sha256: MEDIAPIPE_ASSET_PINS.binarySha256 },
    modelLicenseReview: 'Model licence review — reviewed by the integrator; Apache-2.0 model cards confirmed; nothing fetched at runtime.',
};
const silentWorker = () => ({ terminate: vi.fn(), onmessage: null as unknown, onerror: null as unknown, postMessage: vi.fn() });
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });

describe('vision estimator deadlines', () => {
    it('gives initialization 60 s by default (slow phones and CI emulators need well over 15 s)', async () => {
        vi.useFakeTimers(); vi.stubGlobal('location', { href: 'https://ezo.test/' });
        const worker = silentWorker();
        const init = createVisionEstimator(assets, vi.fn(), { workerFactory: () => worker as unknown as Worker });
        const failed = expect(init).rejects.toThrow('Vision deadline exceeded');
        await vi.advanceTimersByTimeAsync(59_999); expect(worker.terminate).not.toHaveBeenCalled();
        await vi.advanceTimersByTimeAsync(1); await failed; expect(worker.terminate).toHaveBeenCalledOnce();
    });
    it('honours an integrator budget for initialization', async () => {
        vi.useFakeTimers(); vi.stubGlobal('location', { href: 'https://ezo.test/' });
        const worker = silentWorker();
        const init = createVisionEstimator(assets, vi.fn(), { workerFactory: () => worker as unknown as Worker, initTimeoutMs: 20_000 });
        const failed = expect(init).rejects.toThrow('Vision deadline exceeded');
        await vi.advanceTimersByTimeAsync(19_999); expect(worker.terminate).not.toHaveBeenCalled();
        await vi.advanceTimersByTimeAsync(1); await failed; expect(worker.terminate).toHaveBeenCalledOnce();
    });
    it('rejects nonfinite or unbounded budgets before touching a worker', async () => {
        vi.stubGlobal('location', { href: 'https://ezo.test/' });
        for (const bad of [Infinity, NaN, 0, 999, 120_001, -1]) {
            const factory = vi.fn();
            await expect(createVisionEstimator(assets, vi.fn(), { workerFactory: factory, initTimeoutMs: bad })).rejects.toThrow('Invalid vision deadline');
            await expect(createVisionEstimator(assets, vi.fn(), { workerFactory: factory, frameTimeoutMs: bad })).rejects.toThrow('Invalid vision deadline');
            expect(factory).not.toHaveBeenCalled();
        }
    });
});
