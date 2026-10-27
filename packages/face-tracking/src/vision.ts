import type { Estimator } from './index';
import type { PerceptionFrame } from './types';
export const MEDIAPIPE_ASSET_PINS = Object.freeze({ version: '0.10.32', loaderSha256: '9f8fc960e363f0fb2f42f7937b97ae9cf9a5630490f71031fa90caa9bb121938', binarySha256: '924274fcd5ac8985f6570a8573e7971b7bd2d580ba1b8f3beb0ba8f95db6347c' });
export interface VerifiedAsset {
    url: string;
    sha256: string;
}
/** Supplied by reviewed local asset preparation, NEVER CDN URLs or model-generated configuration. */
export interface VisionAssets {
    face: VerifiedAsset;
    hand: VerifiedAsset;
    wasmLoader: VerifiedAsset;
    wasmBinary: VerifiedAsset;
    /** Separate model terms must have been reviewed by the integrator. SDK Apache is insufficient. */
    modelLicenseReview: string;
}
export function validateAssets(assets: VisionAssets, origin: string) {
    if (assets.wasmLoader.sha256 !== MEDIAPIPE_ASSET_PINS.loaderSha256 || assets.wasmBinary.sha256 !== MEDIAPIPE_ASSET_PINS.binarySha256)
        throw new Error('Only reviewed MediaPipe 0.10.32 non-SIMD CPU runtime is supported');
    if (!assets.modelLicenseReview.trim())
        throw new Error('Face/hand model license review required');
    for (const asset of [assets.face, assets.hand, assets.wasmLoader, assets.wasmBinary]) {
        const url = new URL(asset.url, origin);
        if (url.origin !== new URL(origin).origin || url.username || url.password || !/^https?:$/.test(url.protocol) || !/^([a-f0-9]{64})$/.test(asset.sha256))
            throw new Error('Only SHA256-pinned same-origin vision assets are allowed');
    }
}
/** One transferable bitmap at a time. Inference runs only in a dedicated, terminable worker. */
export async function createVisionEstimator(assets: VisionAssets, onFrame: (frame: PerceptionFrame) => void, options: {
    signal?: AbortSignal;
    workerFactory?: () => Worker;
} = {}): Promise<Estimator> {
    validateAssets(assets, location.href);
    if (options.signal?.aborted)
        throw new Error('Vision initialization cancelled');
    const worker = options.workerFactory?.() ?? new Worker(new URL('./vision.worker.ts', import.meta.url));
    let closed = false;
    let pending: {
        resolve: (value: PerceptionFrame) => void;
        reject: (reason: Error) => void;
    } | null = null;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let sequence = 0;
    let handTargetAt=-Infinity;
    const clear = () => { if (timer !== undefined)
        clearTimeout(timer); timer = undefined; };
    const close = () => { if (closed)
        return; closed = true; options.signal?.removeEventListener('abort', close); clear(); pending?.reject(new Error('Vision worker closed')); pending = null; worker.terminate(); };
    options.signal?.addEventListener('abort', close, { once: true });
    worker.onerror = () => { pending?.reject(new Error('Vision worker failed')); pending = null; close(); };
    worker.onmessage = (e: MessageEvent<{
        type: string;
        id: number;
        frame: PerceptionFrame;
        error?: string;
    }>) => {
        if (e.data.id !== sequence || !pending)
            return;
        clear();
        const p = pending;
        pending = null;
        if (e.data.type === 'error')
            p.reject(new Error(e.data.error ?? 'Vision inference failed'));
        else
            p.resolve(e.data.frame);
    };
    const request = (message: object, transfer: Transferable[] = []) => new Promise<PerceptionFrame>((resolve, reject) => {
        if (closed || pending) {
            reject(new Error('Vision unavailable or busy'));
            return;
        }
        pending = { resolve, reject };
        timer = setTimeout(() => { pending?.reject(new Error('Vision deadline exceeded')); pending = null; close(); }, 15000);
        try {
            worker.postMessage({ ...message, id: ++sequence }, transfer);
        }
        catch (e) {
            clear();
            pending = null;
            reject(e);
        }
    });
    try {
        await request({ type: 'init', assets, origin: location.href, });
    }
    catch (e) {
        close();
        throw e;
    }
    return {
        async estimate(video, time) {
            if (closed)
                throw new Error('Vision worker closed');
            const bitmap = await createImageBitmap(video);
            if (closed) {
                bitmap.close();
                throw new Error('Vision worker closed');
            }
            try {
                const frame = await request({ type: 'frame', bitmap, time }, [bitmap]);
                if (closed)
                    return null;
                handTargetAt=frame.hands.some(h=>h.confidence>=0.6)?frame.timestampMs:-Infinity;
                onFrame(frame);
                return frame.face;
            }
            finally {
                bitmap.close();
            }
        }, hasTarget:()=>!closed&&performance.now()-handTargetAt<=500, close,
    };
}
