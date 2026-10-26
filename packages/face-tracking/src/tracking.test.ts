import {describe,it,expect,vi} from 'vitest';
import {pose,Smoother,mediaPipeEstimator,driveAvatar,CameraTracker} from './index';
const identity=[1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1];
describe('synthetic pose contracts (not camera validation)',()=>{
 it('neutral and invalid matrices',()=>{expect(pose(identity,1)?.yaw).toBe(0);expect(pose([NaN],1)).toBeNull();});
 it('rotation produces bounded signed head aim',()=>{const m=[...identity];m[8]=1;m[10]=0;expect(pose(m,1)?.yaw).toBe(1);});
 it('smooths and fences stale timestamps',()=>{const s=new Smoother();const f=pose(identity,1)!;s.update(f);const n=s.update({...f,yaw:1,timestamp:11});expect(n.yaw).toBeGreaterThan(0);expect(n.yaw).toBeLessThan(1);expect(s.update(f)).toBe(n);s.reset();expect(s.update(f)).toEqual(f);});
 it('lost/multiple faces clear output and closes model',()=>{const close=vi.fn();const l={detectForVideo:()=>({faceLandmarks:[],facialTransformationMatrixes:[]}),close};const e=mediaPipeEstimator(l);expect(e.estimate({} as HTMLVideoElement,1)).toBeNull();e.close();expect(close).toHaveBeenCalledOnce();});
 it('adapter clamps and clears without touching avatar state',()=>{const setHeadAim=vi.fn();driveAvatar({setHeadAim},{...pose(identity,1)!,yaw:4});expect(setHeadAim).toHaveBeenLastCalledWith({yawRadians:0.25,pitchRadians:0,rollRadians:0});driveAvatar({setHeadAim},null);expect(setHeadAim).toHaveBeenLastCalledWith(null);});
});
describe('permission lifecycle with mocked camera, NOT physical hardware',()=>{
 it('stops a late permission grant after disable, without loading inference',async()=>{
 vi.stubGlobal('document',{hidden:false,addEventListener:vi.fn(),removeEventListener:vi.fn()});vi.stubGlobal('isSecureContext',true);
 let resolve!:(s:MediaStream)=>void;const getUserMedia=vi.fn(()=>new Promise<MediaStream>(r=>{resolve=r;}));vi.stubGlobal('navigator',{mediaDevices:{getUserMedia}});
 const stop=vi.fn();const video={pause:vi.fn(),play:vi.fn(),srcObject:null} as unknown as HTMLVideoElement;const createEstimator=vi.fn();const t=new CameraTracker({video,indicator:{} as HTMLElement,createEstimator,onFrame:vi.fn()});
 expect(getUserMedia).not.toHaveBeenCalled();const pending=t.start();t.stop();resolve({getTracks:()=>[{stop}]} as unknown as MediaStream);await pending;expect(stop).toHaveBeenCalledOnce();expect(createEstimator).not.toHaveBeenCalled();vi.unstubAllGlobals();
 });
});
it('model failure releases an acquired camera and reports error',async()=>{
 vi.stubGlobal('document',{hidden:false,addEventListener:vi.fn(),removeEventListener:vi.fn()});vi.stubGlobal('isSecureContext',true);
 const stop=vi.fn();const stream={getTracks:()=>[{stop}],getVideoTracks:()=>[{addEventListener:vi.fn()}]};
 vi.stubGlobal('navigator',{mediaDevices:{getUserMedia:vi.fn(async()=>stream)}});
 const status=vi.fn();const video={pause:vi.fn(),play:vi.fn(async()=>{}),srcObject:null} as unknown as HTMLVideoElement;
 const t=new CameraTracker({video,indicator:{} as HTMLElement,createEstimator:async()=>{throw new Error('Model unavailable');},onFrame:vi.fn(),onStatus:status});
 await t.start();expect(stop).toHaveBeenCalledOnce();expect(video.srcObject).toBeNull();expect(status).toHaveBeenLastCalledWith('error','Model unavailable');vi.unstubAllGlobals();
});
it('hidden view never requests a camera',async()=>{
 vi.stubGlobal('document',{hidden:false,removeEventListener:vi.fn()});const getUserMedia=vi.fn();vi.stubGlobal('navigator',{mediaDevices:{getUserMedia}});
 const t=new CameraTracker({video:{pause:vi.fn()} as unknown as HTMLVideoElement,indicator:{} as HTMLElement,createEstimator:vi.fn(),onFrame:vi.fn()});t.setVisible(false);await t.start();expect(getUserMedia).not.toHaveBeenCalled();vi.unstubAllGlobals();
});
it('late model initialization is closed after stop',async()=>{
 vi.stubGlobal('document',{hidden:false,addEventListener:vi.fn(),removeEventListener:vi.fn()});vi.stubGlobal('isSecureContext',true);
 const stop=vi.fn();vi.stubGlobal('navigator',{mediaDevices:{getUserMedia:async()=>({getTracks:()=>[{stop}],getVideoTracks:()=>[{addEventListener:vi.fn()}]})}});
 let resolve!:(e:ReturnType<typeof mediaPipeEstimator>)=>void;const createEstimator=vi.fn(()=>new Promise<ReturnType<typeof mediaPipeEstimator>>(r=>{resolve=r;}));
 const t=new CameraTracker({video:{pause:vi.fn(),play:async()=>{}} as unknown as HTMLVideoElement,indicator:{} as HTMLElement,createEstimator,onFrame:vi.fn()});const pending=t.start();await vi.waitFor(()=>expect(createEstimator).toHaveBeenCalledOnce());t.stop();const close=vi.fn();resolve({estimate:()=>null,close});await pending;expect(stop).toHaveBeenCalledOnce();expect(close).toHaveBeenCalledOnce();vi.unstubAllGlobals();
});
it('granted stream emits a derived frame and hidden avatar stops capture',async()=>{
 vi.useFakeTimers();vi.stubGlobal('document',{hidden:false,addEventListener:vi.fn(),removeEventListener:vi.fn()});vi.stubGlobal('isSecureContext',true);
 const stop=vi.fn(),close=vi.fn(),onFrame=vi.fn();vi.stubGlobal('navigator',{mediaDevices:{getUserMedia:async()=>({getTracks:()=>[{stop}],getVideoTracks:()=>[{addEventListener:vi.fn()}]})}});
 const video={pause:vi.fn(),play:async()=>{},readyState:2,currentTime:1} as unknown as HTMLVideoElement;
 const t=new CameraTracker({video,indicator:{} as HTMLElement,createEstimator:async()=>({estimate:(_v,time)=>pose(identity,time),close}),onFrame});await t.start();expect(onFrame.mock.lastCall?.[0]?.confidence).toBe(1);t.setVisible(false);expect(stop).toHaveBeenCalledOnce();expect(close).toHaveBeenCalledOnce();expect(vi.getTimerCount()).toBe(0);expect(onFrame).toHaveBeenLastCalledWith(null);vi.useRealTimers();vi.unstubAllGlobals();
});
