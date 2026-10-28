import {runInNewContext} from 'node:vm';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { clapProcessorSource, ClapMicrophone } from './microphone';
import { ClapDetector } from './clap';
import { acknowledgement, VoiceReaction } from './voice';
import type { ClapDetected } from './types';
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });
const pcm = (length: number, value = 0) => new Float32Array(length).map((_, i) => i % 2 ? value : -value);
function clap(d: ClapDetector, time: number) { d.push(pcm(480), 48000, time); d.push(pcm(480, 0.7), 48000, time + 10); return d.push(pcm(960), 48000, time + 20); }
describe('synthetic acoustic evidence, not real clap validation', () => {
    it('emits only after short high-frequency transient decays', () => { const d = new ClapDetector(); d.push(pcm(480), 48000, 0); expect(d.push(pcm(480, 0.7), 48000, 10)).toEqual([]); expect(d.push(pcm(960), 48000, 20)).toMatchObject([{ type: 'clap_detected', authorization: 'acknowledgement_only', evidence: 'acoustic_transient' }]); });
    it('rejects silence, low noise, sustained speech-like sine, and constant sharp noise', () => { const d = new ClapDetector(); let events: ClapDetected[] = []; for (let i = 0; i < 100; i++)
        events.push(...d.push(pcm(480, 0.01), 48000, i * 10)); for (let i = 0; i < 100; i++)
        events.push(...d.push(new Float32Array(480).map((_, j) => Math.sin((i * 480 + j) * 2 * Math.PI * 180 / 48000) * 0.5), 48000, 1000 + i * 10)); for (let i = 0; i < 100; i++)
        events.push(...d.push(pcm(480, 0.7), 48000, 2000 + i * 10)); expect(events).toEqual([]); });
    it('debounces repeated claps, allows a later clap, and rejects stale/invalid PCM', () => { const d = new ClapDetector(); expect(clap(d, 0)).toHaveLength(1); expect(clap(d, 100)).toHaveLength(0); expect(clap(d, 1500)).toHaveLength(1); expect(d.push(pcm(480, 0.9), 48000, 10)).toEqual([]); expect(d.push(new Float32Array([NaN]), 48000, 2000)).toEqual([]); expect(d.push(pcm(480), 0, 2010)).toEqual([]); });
    it('bounds input and validates sensitivity', () => { expect(() => new ClapDetector({ sensitivity: 0 })).toThrow(); expect(() => new ClapDetector({ cooldownMs: 10 })).toThrow(); expect(new ClapDetector().push(pcm(48001), 48000, 0)).toEqual([]); });
});

describe('acknowledgements and actual-playback boundary', () => {
    const event: ClapDetected = { type: 'clap_detected', timestampMs: 1, confidence: 0.8, evidence: 'acoustic_transient', authorization: 'acknowledgement_only' };
    it.each([['uz', 'Eshitaman seni.'], ['en', "I'm listening."], ['ru', 'Я тебя слушаю.']] as const)('uses selected language %s, no listening authorization', (lang, text) => { expect(acknowledgement(event, lang)).toMatchObject({ text, startListening: false, authorization: 'acknowledgement_only' }); });
    it('provider unavailable is not pretend audio playback', async () => { const output = vi.fn(); await new VoiceReaction(null, output).react(acknowledgement(event, 'uz')); expect(output).toHaveBeenCalledOnce(); expect(output.mock.calls[0]![0].type).toBe('unavailable'); });
    it('forwards only real bounded audio levels and cancels stale playback', async () => { const output = vi.fn(); let send!: (event: any) => void; let resolve!: () => void; const reaction = new VoiceReaction({ play: async (_i, _s, emit) => { send = emit; await new Promise<void>(r => { resolve = r; }); } }, output); const pending = reaction.react(acknowledgement(event, 'en')); send({ type: 'level', level: 1, timestampMs: 0 }); expect(output).not.toHaveBeenCalled(); send({ type: 'start', timestampMs: 1 }); send({ type: 'level', level: 3, timestampMs: 2 }); expect(output.mock.lastCall![0].level).toBe(1); reaction.stop(); const count = output.mock.calls.length; send({ type: 'level', level: 1, timestampMs: 4 }); expect(output).toHaveBeenCalledTimes(count); resolve(); await pending; });
    it('rejects unverified confidence and reports player errors', async () => { expect(() => acknowledgement({ ...event, confidence: 0.2 }, 'uz')).toThrow(); const output = vi.fn(); await new VoiceReaction({ play: async () => { throw new Error('offline'); } }, output).react(acknowledgement(event, 'en')); expect(output.mock.lastCall![0].type).toBe('error'); });
});

function environment() { const doc = new EventTarget() as EventTarget & {
    hidden: boolean;
}; doc.hidden = false; vi.stubGlobal('document', doc); vi.stubGlobal('isSecureContext', true); return doc; }
function streamMock() { const track = Object.assign(new EventTarget(), { stop: vi.fn() }); return { track, stream: { getTracks: () => [track], getVideoTracks: () => [track], getAudioTracks: () => [track] } as unknown as MediaStream }; }

describe('sensor privacy lifecycle', () => {
    it('microphone is separate and OFF on construction; late grant is stopped', async () => { environment(); let resolve!: (s: MediaStream) => void; const getUserMedia = vi.fn(() => new Promise<MediaStream>(r => { resolve = r; })); vi.stubGlobal('navigator', { mediaDevices: { getUserMedia } }); const t = new ClapMicrophone({ indicator: {} as HTMLElement, onClap: vi.fn() }); expect(getUserMedia).not.toHaveBeenCalled(); const pending = t.start(); expect(getUserMedia.mock.calls[0]).toEqual([{ video: false, audio: expect.any(Object) }]); t.stop(); const { track, stream } = streamMock(); resolve(stream); await pending; expect(track.stop).toHaveBeenCalledOnce(); });
    it('microphone denial does not retry', async () => { environment(); const getUserMedia = vi.fn(async () => { throw new Error('denied'); }); vi.stubGlobal('navigator', { mediaDevices: { getUserMedia } }); const status = vi.fn(); await new ClapMicrophone({ indicator: {} as HTMLElement, onClap: vi.fn(), onStatus: status }).start(); expect(getUserMedia).toHaveBeenCalledOnce(); expect(status.mock.lastCall).toEqual(['error', 'denied']); });
    it('audio initialization failure releases granted microphone', async () => { environment(); const { track, stream } = streamMock(); vi.stubGlobal('navigator', { mediaDevices: { getUserMedia: async () => stream } }); vi.stubGlobal('AudioContext', class {
        constructor() { throw new Error('worklet unavailable'); }
    }); const status = vi.fn(); await new ClapMicrophone({ indicator: {} as HTMLElement, onClap: vi.fn(), onStatus: status }).start(); expect(track.stop).toHaveBeenCalledOnce(); expect(status.mock.lastCall).toEqual(['error', 'worklet unavailable']); });
    it('audio hide/revocation and repeated start/stop close graph, port and tracks', async () => { const doc = environment(); const { track, stream } = streamMock(); vi.stubGlobal('navigator', { mediaDevices: { getUserMedia: async () => stream } }); const disconnect = vi.fn(), close = vi.fn(async () => { }), portClose = vi.fn(); vi.stubGlobal('AudioContext', class {
        audioWorklet = { addModule: async () => { } };
        currentTime = 0;
        destination = {};
        sampleRate = 48000;
        resume = async () => { };
        close = close;
        createMediaStreamSource = () => ({ connect: vi.fn(), disconnect });
    }); vi.stubGlobal('AudioWorkletNode', class {
        port = { onmessage: null, close: portClose };
        connect = vi.fn();
        disconnect = disconnect;
    }); const t = new ClapMicrophone({ indicator: {} as HTMLElement, onClap: vi.fn() }); for (let i = 0; i < 3; i++) {
        await t.start();
        t.stop();
    } expect(close).toHaveBeenCalledTimes(3); expect(portClose).toHaveBeenCalledTimes(3); await t.start(); doc.hidden = true; doc.dispatchEvent(new Event('visibilitychange')); expect(close).toHaveBeenCalledTimes(4); doc.hidden = false; await t.start(); track.dispatchEvent(new Event('ended')); expect(close).toHaveBeenCalledTimes(5); });
});
it('bounds audio-thread backlog to one unacknowledged PCM window',()=>{
 let Processor:any;const postMessage=vi.fn();
 runInNewContext(clapProcessorSource,{AudioWorkletProcessor:class {port={postMessage,onmessage:null};},registerProcessor:(_name:string,implementation:any)=>{Processor=implementation;},sampleRate:48000,currentFrame:0,Float32Array});
 const instance=new Processor();const input=[[new Float32Array(128)]];
 for(let i=0;i<100;i++)instance.process(input,[]);
 expect(postMessage).toHaveBeenCalledOnce();
 instance.port.onmessage({data:'ack'});
 for(let i=0;i<4;i++)instance.process(input,[]);
 expect(postMessage).toHaveBeenCalledTimes(2);
});
it('acknowledges dropped stale/suppressed audio without treating it as fresh clap evidence',async()=>{
 vi.spyOn(performance,'now').mockReturnValue(1000);environment();const {stream}=streamMock();vi.stubGlobal('navigator',{mediaDevices:{getUserMedia:async()=>stream}});
 const port={onmessage:null as any,postMessage:vi.fn(),close:vi.fn()};
 vi.stubGlobal('AudioContext',class {audioWorklet={addModule:async()=>{}};currentTime=0;destination={};sampleRate=48000;resume=async()=>{};close=async()=>{};createMediaStreamSource=()=>({connect:vi.fn(),disconnect:vi.fn()});});
 vi.stubGlobal('AudioWorkletNode',class {port=port;connect=vi.fn();disconnect=vi.fn();});
 const detector=new ClapDetector(),push=vi.spyOn(detector,'push');const mic=new ClapMicrophone({indicator:{} as HTMLElement,detector,onClap:vi.fn()});await mic.start();
 port.onmessage({data:{samples:new Float32Array(480),time:-1000}});expect(push).not.toHaveBeenCalled();
 mic.setSuppressed(true);port.onmessage({data:{samples:new Float32Array(480),time:0}});expect(push).not.toHaveBeenCalled();
 mic.setSuppressed(false);port.onmessage({data:{samples:new Float32Array(480),time:0}});expect(push).toHaveBeenCalledOnce();expect(port.postMessage).toHaveBeenCalledTimes(3);mic.stop();
});

it('cancels pending microphone permission on backgrounding, before a late grant',async()=>{
 const doc=environment();let resolve!:(stream:MediaStream)=>void;const getUserMedia=vi.fn(()=>new Promise<MediaStream>(r=>{resolve=r;}));vi.stubGlobal('navigator',{mediaDevices:{getUserMedia}});
 const status=vi.fn();const tracker=new ClapMicrophone({indicator:{} as HTMLElement,onClap:vi.fn(),onStatus:status});
 const pending=tracker.start();doc.hidden=true;doc.dispatchEvent(new Event('visibilitychange'));expect(status.mock.lastCall![0]).toBe('off');
 const {track,stream}=streamMock();resolve(stream);await pending;expect(track.stop).toHaveBeenCalledOnce();
});

