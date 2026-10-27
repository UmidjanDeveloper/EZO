import { FaceLandmarker, HandLandmarker } from '@mediapipe/tasks-vision';
import { faceFrame, HandMotionTracker } from './landmarks';
import type { VisionAssets, VerifiedAsset } from './vision';
import { validateAssets } from './vision';
import type { PerceptionFrame } from './types';
// Classic bundled worker: Tasks Vision uses importScripts for its WASM loader.
const scope = globalThis as unknown as {
    onmessage: ((event: MessageEvent) => void) | null;
    postMessage: (message: object) => void;
    location: Location;
};
let face: FaceLandmarker | null = null, hand: HandLandmarker | null = null;
const handMotion = new HandMotionTracker();
const urls: string[] = [];
async function verified(asset: VerifiedAsset, origin: string, maxBytes: number): Promise<Uint8Array> {
    const response = await fetch(new URL(asset.url, origin), { credentials: 'omit', redirect: 'error', cache: 'no-store' });
    if (!response.ok || !response.body)
        throw new Error('Vision asset unavailable');
    const reader = response.body.getReader(), chunks: Uint8Array[] = [];
    let size = 0;
    try {
        while (true) {
            const { value, done } = await reader.read();
            if (done)
                break;
            size += value.byteLength;
            if (size > maxBytes)
                throw new Error('Vision asset too large');
            chunks.push(value);
        }
    }
    finally {
        await reader.cancel();
    }
    const data = new Uint8Array(size);
    let offset = 0;
    for (const chunk of chunks) {
        data.set(chunk, offset);
        offset += chunk.byteLength;
    }
    const digest = new Uint8Array(await crypto.subtle.digest('SHA-256', data));
    if (Array.from(digest, b => b.toString(16).padStart(2, '0')).join('') !== asset.sha256)
        throw new Error('Vision asset SHA256 mismatch');
    return data;
}
const blobUrl = (data: Uint8Array, type: string) => { const url = URL.createObjectURL(new Blob([data as BlobPart], { type })); urls.push(url); return url; };
scope.onmessage = async (event: MessageEvent) => {
    const message = event.data as {
        type: string;
        id: number;
        assets: VisionAssets;
        origin: string;
        bitmap: ImageBitmap;
        time: number;
        lowPower: boolean;
    };
    try {
        if (message.type === 'init') {
            if (face || hand)
                throw new Error('Already initialized');
            validateAssets(message.assets, message.origin);
            const a = message.assets;
            const [loader, binary, faceModel, handModel] = await Promise.all([verified(a.wasmLoader, message.origin, 2000000), verified(a.wasmBinary, message.origin, 20000000), verified(a.face, message.origin, 12000000), verified(a.hand, message.origin, 12000000)]);
            const files = { wasmLoaderPath: blobUrl(loader, 'text/javascript'), wasmBinaryPath: blobUrl(binary, 'application/wasm') };
            face = await FaceLandmarker.createFromOptions(files, { baseOptions: { modelAssetBuffer: faceModel, delegate: 'CPU' }, runningMode: 'VIDEO', numFaces: 1, outputFacialTransformationMatrixes: true, minFaceDetectionConfidence: 0.6, minFacePresenceConfidence: 0.6, minTrackingConfidence: 0.6 });
            hand = await HandLandmarker.createFromOptions(files, { baseOptions: { modelAssetBuffer: handModel, delegate: 'CPU' }, runningMode: 'VIDEO', numHands: 2, minHandDetectionConfidence: 0.6, minHandPresenceConfidence: 0.6, minTrackingConfidence: 0.6 });
            scope.postMessage({ type: 'ready', id: message.id });
        }
        else if (message.type === 'frame') {
            if (!face || !hand)
                throw new Error('Vision not initialized');
            const started = performance.now(), t = message.time;
            if (!Number.isFinite(t))
                throw new Error('Invalid frame time');
            const f = face.detectForVideo(message.bitmap, t), h = hand.detectForVideo(message.bitmap, t);
            const tracked = faceFrame(f.faceLandmarks, f.facialTransformationMatrixes, t);
            const hands = handMotion.update(h.landmarks, h.handedness, t);
            const frame: PerceptionFrame = { face: tracked, hands, timestampMs: t, inferenceMs: performance.now() - started };
            if (hands.length === 2)
                frame.handsDistance = Math.hypot(hands[0]!.x - hands[1]!.x, hands[0]!.y - hands[1]!.y);
            scope.postMessage({ type: 'frame', id: message.id, frame });
        }
        else
            throw new Error('Unknown worker request');
    }
    catch (error) {
        face?.close();
        hand?.close();
        face = null;
        hand = null;
        for (const url of urls)
            URL.revokeObjectURL(url);
        urls.length = 0;
        scope.postMessage({ type: 'error', id: message.id, error: error instanceof Error ? error.message : 'Vision failed' });
    }
    finally {
        message.bitmap?.close();
    }
};
