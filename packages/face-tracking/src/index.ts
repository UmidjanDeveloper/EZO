import {watchRevocation} from './permissions';
/** All angles/targets are normalized [-1,1], NOT measured gaze or degrees. */
export interface TrackingFrame { yaw:number; pitch:number; roll:number; gazeX:number; gazeY:number; confidence:number; timestamp:number }
export type TrackingStatus = 'off'|'requesting'|'tracking'|'lost'|'error';
export interface Estimator { estimate(video:HTMLVideoElement,time:number):TrackingFrame|null|Promise<TrackingFrame|null>; hasTarget?():boolean; close():void }
import { clamp, pose } from './pose';
export { clamp, pose } from './pose';
export class Smoother {
  private last:TrackingFrame|null=null;
  reset(){this.last=null;}
  update(f:TrackingFrame):TrackingFrame {
    const prior=this.last;
    if(prior && f.timestamp<=prior.timestamp) return prior;
    const a=prior ? 1-Math.exp(-Math.min(250,f.timestamp-prior.timestamp)/100):1;
    const out={...f};
    for(const k of ['yaw','pitch','roll','gazeX','gazeY'] as const) out[k]=clamp(prior ? prior[k]+a*(f[k]-prior[k]):f[k]);
    this.last=out;return out;
  }
}
export interface TrackerOptions {
  video:HTMLVideoElement;
  /** Must remain visible while capture is active. Engine owns indicator text. */
  indicator:HTMLElement;
  createEstimator:(signal:AbortSignal)=>Promise<Estimator>;
  lowPower?:boolean;
  onFrame:(frame:TrackingFrame|null)=>void;
  onStatus?:(status:TrackingStatus,error?:string)=>void;
}
export class CameraTracker {
  private stream:MediaStream|null=null;
  private estimator:Estimator|null=null;
  private inferenceAbort:AbortController|null=null;
  private generation=0;
  private timer:ReturnType<typeof setTimeout>|undefined;
  private smooth=new Smoother();
  private visible=true;
  private interval=100;
  private lastVideoTime=-1;
  private lastSampleTime=-Infinity;
  private status:TrackingStatus='off';
  private trackListeners:{track:MediaStreamTrack;listener:()=>void}[]=[];
  private readonly pagehide=()=>this.stop();
  private readonly hide=()=>{if(document.hidden)this.stop();};
  constructor(private readonly options:TrackerOptions){}
  private state(status:TrackingStatus,error?:string){
    this.status=status;
    this.options.indicator.textContent=this.stream ? `Camera active — ${status}`:`Camera ${status}`;
    this.options.indicator.hidden=false;
    this.options.onStatus?.(status,error);
  }
  /** Call only from an explicit user click. No constructor/autostart capture. */
  async start():Promise<void>{
    if(this.status!=='off' && this.status!=='error') return;
    this.stop();const token=++this.generation;
    const abort=new AbortController();this.inferenceAbort=abort;
    try{
      if(document.hidden || !this.visible) throw new Error('Tracking view is hidden');
      if(!globalThis.isSecureContext || !navigator.mediaDevices?.getUserMedia) throw new Error('Secure camera API unavailable');
      this.state('requesting');
      document.addEventListener('visibilitychange',this.hide);
      globalThis.addEventListener?.('pagehide',this.pagehide);
      const stream=await navigator.mediaDevices.getUserMedia({audio:false,video:{facingMode:'user',width:{ideal:this.options.lowPower?320:640,max:640},height:{ideal:this.options.lowPower?240:480,max:480},frameRate:{ideal:this.options.lowPower?8:15,max:this.options.lowPower?8:15}}});
      if(token!==this.generation||document.hidden||!this.visible){stream.getTracks().forEach(t=>t.stop());if(token===this.generation)this.stop();return;}
      this.stream=stream;this.state('requesting');
      watchRevocation('camera',abort.signal,()=>{if(token===this.generation)this.fail('Camera permission revoked');});
      for(const track of stream.getVideoTracks()) { const listener=()=>{if(token===this.generation)this.fail('Camera disconnected or interrupted');}; track.addEventListener('ended',listener,{once:true});track.addEventListener('mute',listener,{once:true}); this.trackListeners.push({track,listener}); }
      this.options.video.srcObject=stream;this.options.video.muted=true;this.options.video.playsInline=true;
      await this.options.video.play();
      if(token!==this.generation)return;
      const estimator=await this.options.createEstimator(abort.signal);
      if(token!==this.generation){estimator.close();return;}
      this.estimator=estimator;void this.tick(token);
    }catch(e){if(token===this.generation)this.fail(e instanceof Error?e.message:'Camera tracking failed');}
  }
  private fail(message:string){this.stop();this.state('error',message);}
  private async tick(token:number){
    if(token!==this.generation)return;
    if(document.hidden || !this.visible){this.stop();return;}
    try{
      const video=this.options.video;
      const start=performance.now();
      if(video.readyState>=2 && video.currentTime!==this.lastVideoTime){
        this.lastVideoTime=video.currentTime;this.lastSampleTime=start;
        const f=await this.estimator!.estimate(video,start);
        if(token!==this.generation)return;
        const valid=f && Object.values(f).every(Number.isFinite) && f.confidence>=0.5 && f.timestamp<=performance.now() && performance.now()-f.timestamp<=500;
        this.state(valid||this.estimator?.hasTarget?.()?'tracking':'lost');
        this.options.onFrame(valid?this.smooth.update(f):null);
        if(!valid)this.smooth.reset();
      }else if(start-this.lastSampleTime>500){
        this.state('lost');this.options.onFrame(null);this.smooth.reset();
      } // A single duplicate is normal; a frozen stream expires on the monotonic clock.
      if(token!==this.generation)return;
      this.interval=Math.min(250,Math.max(this.options.lowPower?125:66,0.8*this.interval+0.2*(performance.now()-start)*2));
      this.timer=setTimeout(()=>void this.tick(token),this.interval);
    }catch(e){if(token===this.generation)this.fail(e instanceof Error?e.message:'Inference failed');}
  }
  /** Hidden avatar stops capture; making visible never re-enables camera automatically. */
  setVisible(visible:boolean){this.visible=visible;if(!visible)this.stop();}
  stop(){
    ++this.generation;this.inferenceAbort?.abort();this.inferenceAbort=null;
    for(const {track,listener} of this.trackListeners){track.removeEventListener?.('ended',listener);track.removeEventListener?.('mute',listener);}this.trackListeners=[];
    globalThis.removeEventListener?.('pagehide',this.pagehide);
    if(this.timer!==undefined)clearTimeout(this.timer);this.timer=undefined;
    this.stream?.getTracks().forEach(t=>t.stop());this.stream=null;
    this.options.video.pause();this.options.video.srcObject=null;
    try{this.estimator?.close();}catch{/* Camera tracks are already released; finish disposal even if model close fails. */}finally{this.estimator=null;this.smooth.reset();this.lastVideoTime=-1;this.lastSampleTime=-Infinity;this.interval=100;document.removeEventListener('visibilitychange',this.hide);this.state('off');this.options.onFrame(null);}
  }
}
export interface Landmarker {
  detectForVideo(video:HTMLVideoElement,time:number):{faceLandmarks:{x:number;y:number}[][];facialTransformationMatrixes:{data: number[]}[]};
  close():void;
}
/** Pass an actual tasks-vision FaceLandmarker configured for VIDEO/one face. */
export function mediaPipeEstimator(landmarker:Landmarker):Estimator {
  return {estimate(video,time){const result=landmarker.detectForVideo(video,time);if(result.faceLandmarks.length!==1)return null;
    const frame=pose(result.facialTransformationMatrixes[0]?.data??[],time);
    const nose=result.faceLandmarks[0]?.[1];
    // Face position target in unmirrored camera coordinates; not iris gaze.
    if(frame && nose && Number.isFinite(nose.x) && Number.isFinite(nose.y)){
      frame.gazeX=clamp((nose.x-0.5)*2);frame.gazeY=clamp((0.5-nose.y)*2);
    }
    return frame;},close(){landmarker.close();}};
}
/** Future renderer port, NOT a currently exported EzoAvatar method. */
export interface MotionPort { setHeadAim(aim:{yawRadians:number;pitchRadians:number;rollRadians:number}|null):void }
export function driveAvatar(port:MotionPort,frame:TrackingFrame|null){
  port.setHeadAim(frame ? {yawRadians:clamp(frame.yaw)*0.25,pitchRadians:clamp(frame.pitch)*0.15,rollRadians:clamp(frame.roll)*0.1}:null);
}

export * from './types';
export * from './attention';
export * from './clap';
export * from './microphone';
export * from './voice';
export * from './vision';
export * from './perception';
export * from './landmarks';
