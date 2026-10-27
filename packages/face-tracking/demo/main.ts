import {EzoAvatar} from '../../avatar/src/index';
import {CameraTracker,AttentionController,ClapMicrophone,VoiceReaction,acknowledgement,createVisionEstimator,applyMotion} from '../src/index';
import type {Language,VisionAssets} from '../src/index';
const element=<T extends HTMLElement>(id:string)=>document.getElementById(id) as T;
const error=element('error'),output=element('output'),video=element<HTMLVideoElement>('video');
const avatar=new EzoAvatar(element<HTMLCanvasElement>('avatar'),{framing:'bust'});
const reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;
const attention=new AttentionController({mirrored:true,reducedMotion:reduced});
const voice=new VoiceReaction(null,event=>{element('voice').textContent=`Voice ${event.type}: no provider connected; acknowledgement not spoken.`;});
function respond(event:Parameters<typeof acknowledgement>[0]){const intent=acknowledgement(event,element<HTMLSelectElement>('language').value as Language);element('voice').textContent=`Requested: ${intent.text} — not spoken (no authenticated provider playback bridge configured)`;void voice.react(intent);}
const microphone=new ClapMicrophone({indicator:element('microphoneStatus'),onClap:respond,onStatus:(_s,message)=>{if(message)error.textContent=message;}});
const camera=new CameraTracker({video,indicator:element('cameraStatus'),lowPower:true,onStatus:(_s,message)=>{if(message)error.textContent=message;},onFrame:()=>{},createEstimator:async(signal)=>{
 const response=await fetch('./assets/vision-assets.json',{redirect:'error'});if(!response.ok)throw new Error('Reviewed local face/hand assets missing. See prepare-assets.mjs and acceptance guide.');
 const assets:VisionAssets=await response.json();return createVisionEstimator(assets,frame=>{attention.ingest(frame,performance.now());microphone.detector.observeHands(frame.handsDistance,performance.now());output.textContent=JSON.stringify({source:'ACTUAL MODEL OUTPUT — no synthetic substitution',...frame},null,2);},{signal});
}});
let render:number|undefined;
const tick=()=>{applyMotion(avatar,attention.sample(performance.now()));render=requestAnimationFrame(tick);};
const clear=()=>{camera.stop();microphone.stop();voice.stop();attention.reset();avatar.setGaze(null);if(render!==undefined)cancelAnimationFrame(render);render=undefined;output.textContent='Sensors off — no current perception data';};
element('camera').onclick=()=>{error.textContent='';if(render===undefined)tick();void camera.start();};
element('stopCamera').onclick=()=>{camera.stop();attention.reset();avatar.setGaze(null);if(render!==undefined)cancelAnimationFrame(render);render=undefined;};
element('microphone').onclick=()=>void microphone.start();element('stopMicrophone').onclick=()=>microphone.stop();element('stop').onclick=clear;
// Manual intent is labelled manual: it does not fabricate a sensory ClapDetected event.
element('manual').onclick=()=>{const language=element<HTMLSelectElement>('language').value as Language;const text={uz:'Eshitaman seni.',en:"I'm listening.",ru:'Я тебя слушаю.'}[language];element('voice').textContent=`Manual request: ${text} — voice provider unavailable; no audio played.`;};
window.addEventListener('pagehide',()=>{clear();avatar.destroy();});document.addEventListener('visibilitychange',()=>{if(document.hidden)clear();});
