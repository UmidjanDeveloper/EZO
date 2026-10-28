import { ClapDetector } from './clap';
import type { ClapDetected } from './types';
export type MicrophoneStatus = 'off' | 'requesting' | 'active' | 'error';
/** Local PCM never leaves this audio graph. A worklet bounds audio-thread work to one 10ms window. */
export const clapProcessorSource = `class ClapPcm extends AudioWorkletProcessor {
 constructor(){super();this.data=new Float32Array(Math.round(sampleRate/100));this.used=0;this.waiting=false;
 this.port.onmessage=()=>{this.waiting=false;this.used=0;};}
 process(inputs,outputs){for(const output of outputs)for(const ch of output)ch.fill(0);
 if(this.waiting)return true;
 const input=inputs[0]?.[0];if(input)for(let i=0;i<input.length;i++){
 this.data[this.used++]=input[i];if(this.used===this.data.length){
 this.port.postMessage({samples:this.data,time:(currentFrame+i-this.data.length+1)/sampleRate*1000},[this.data.buffer]);
 this.waiting=true;this.data=new Float32Array(Math.round(sampleRate/100));this.used=0;break;}}
 return true;
 }} registerProcessor('ezo-clap-pcm',ClapPcm);`;
export class ClapMicrophone {
    private generation = 0;
    private permissionAbort: AbortController | null = null;
    private stream: MediaStream | null = null;
    private context: AudioContext | null = null;
    private node: AudioWorkletNode | null = null;
    private source: MediaStreamAudioSourceNode | null = null;
    private listeners: {
        track: MediaStreamTrack;
        listener: () => void;
    }[] = [];
    private readonly hide = () => { if (document.hidden)
        this.stop(); };
    private readonly pagehide = () => this.stop();
    private status: MicrophoneStatus = 'off';
    private suppressed = false;
    setSuppressed(suppressed: boolean) { this.suppressed = suppressed; this.detector.reset(); }
    constructor(private readonly options: {
        indicator: HTMLElement;
        detector?: ClapDetector;
        onClap: (event: ClapDetected) => void;
        onStatus?: (status: MicrophoneStatus, error?: string) => void;
    }) { this.detector = options.detector ?? new ClapDetector(); }
    readonly detector: ClapDetector;
    private state(status: MicrophoneStatus, error?: string) { this.status = status; this.options.indicator.hidden = false; this.options.indicator.textContent = `Microphone ${this.stream ? 'active — ' : ''}${status}`; this.options.onStatus?.(status, error); }
    /** Starts only from the owner's own press. Does NOT enable STT/listening. */
    async start(): Promise<void> {
        if (this.status === 'active' || this.status === 'requesting')
            return;
        this.stop();
        const token = ++this.generation;
        const permissionAbort = new AbortController();
        this.permissionAbort = permissionAbort;
        try {
            if (document.hidden || !globalThis.isSecureContext || !navigator.mediaDevices?.getUserMedia)
                throw new Error('Visible secure microphone API unavailable');
            this.state('requesting');
            document.addEventListener('visibilitychange',this.hide);
            globalThis.addEventListener?.('pagehide',this.pagehide);
            const stream = await navigator.mediaDevices.getUserMedia({ video: false, audio: { channelCount: 1, echoCancellation: false, noiseSuppression: false, autoGainControl: false } });
            if (token !== this.generation || document.hidden) {
                stream.getTracks().forEach(t => t.stop());
                if(token===this.generation)this.stop();
                return;
            }
            this.stream = stream;
            watchRevocation('microphone', permissionAbort.signal, () => { if (token === this.generation) {
                this.stop();
                this.state('error', 'Microphone permission revoked');
            } });
            for (const track of stream.getAudioTracks()) {
                const listener = () => { if (token === this.generation) {
                    this.stop();
                    this.state('error', 'Microphone disconnected or interrupted');
                } };
                track.addEventListener('ended', listener, { once: true });
                track.addEventListener('mute', listener, { once: true });
                this.listeners.push({ track, listener });
            }
            this.state('requesting');
            const context = new AudioContext({ latencyHint: 'interactive' });
            this.context = context;
            const url = URL.createObjectURL(new Blob([clapProcessorSource], { type: 'text/javascript' }));
            try {
                await context.audioWorklet.addModule(url);
            }
            finally {
                URL.revokeObjectURL(url);
            }
            if (token !== this.generation)
                return;
            await context.resume();
            if (token !== this.generation)
                return;
            const origin = performance.now() - context.currentTime * 1000;
            const node = new AudioWorkletNode(context, 'ezo-clap-pcm', { numberOfInputs: 1, numberOfOutputs: 1, outputChannelCount: [1] });
            this.node = node;
            node.port.onmessage = (event: MessageEvent<{ samples: Float32Array; time: number }>) => {
                if(token!==this.generation)return;
                try {
                    if(this.suppressed)return;
                    const {samples,time}=event.data;
                    if(!(samples instanceof Float32Array)||samples.length>2048)return;
                    const sampleTime=origin+time,now=performance.now();
                    if(!Number.isFinite(sampleTime)||sampleTime>now+50||now-sampleTime>250)return;
                    for(const clap of this.detector.push(samples,context.sampleRate,origin+time))this.options.onClap(clap);
                } finally {
                    // One message in flight. Busy UI drops input instead of growing the audio queue.
                    if(token===this.generation)node.port.postMessage('ack');
                }
            };
            this.source = context.createMediaStreamSource(stream);
            this.source.connect(node);
            node.connect(context.destination);
            this.state('active');
        }
        catch (e) {
            if (token === this.generation) {
                this.stop();
                this.state('error', e instanceof Error ? e.message : 'Microphone failed');
            }
        }
    }
    stop() {
        ++this.generation;
        this.permissionAbort?.abort();
        this.permissionAbort = null;
        for (const { track, listener } of this.listeners) {
            track.removeEventListener('ended', listener);
            track.removeEventListener('mute', listener);
        }
        this.listeners = [];
        this.stream?.getTracks().forEach(t => t.stop());
        this.stream = null;
        if (this.node) {
            this.node.port.onmessage = null;
            this.node.port.close();
            this.node.disconnect();
            this.node = null;
        }
        this.source?.disconnect();
        this.source = null;
        const context = this.context;
        this.context = null;
        if (context)
            void context.close().catch(() => { });
        document.removeEventListener('visibilitychange', this.hide);
        globalThis.removeEventListener?.('pagehide', this.pagehide);
        this.detector.reset();
        this.state('off');
    }
}

/** Query does not request permission. Unsupported platforms fall back to track ended/mute. */
export function watchRevocation(kind: 'microphone', signal: AbortSignal, onDenied: () => void): void {
    if (!navigator.permissions?.query)
        return;
    void navigator.permissions.query({ name: kind as PermissionName }).then(status => {
        if (signal.aborted)
            return;
        const changed = () => { if (status.state === 'denied' && !signal.aborted)
            onDenied(); };
        status.addEventListener('change', changed);
        signal.addEventListener('abort', () => status.removeEventListener('change', changed), { once: true });
        changed();
    }).catch(() => { });
}
