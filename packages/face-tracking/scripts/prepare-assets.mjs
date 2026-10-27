/** Offline asset preparation. No network downloads, credentials or guessed model licenses. */
import {readFile,writeFile,mkdir,copyFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {createRequire} from 'node:module';
import {dirname,resolve} from 'node:path';
const [facePath,faceHash,handPath,handHash,reviewPath]=process.argv.slice(2);
if(!facePath||!handPath||!reviewPath||!/^([a-f0-9]{64})$/.test(faceHash??'')||!/^([a-f0-9]{64})$/.test(handHash??''))throw new Error('Usage: node scripts/prepare-assets.mjs FACE.task REVIEWED_FACE_SHA256 HAND.task REVIEWED_HAND_SHA256 MODEL_LICENSE_REVIEW.txt');
const review=await readFile(reviewPath,'utf8');if(review.trim().length<80)throw new Error('Provide a real model license/source/distribution review, not a placeholder');
const sha=bytes=>createHash('sha256').update(bytes).digest('hex');
const root=resolve(import.meta.dirname,'../demo/public/assets');await mkdir(root,{recursive:true});
const sdk=dirname(createRequire(import.meta.url).resolve('@mediapipe/tasks-vision'));
const assets={modelLicenseReview:review.trim()};
for(const [key,path,hash,name] of [['face',facePath,faceHash,'face_landmarker.task'],['hand',handPath,handHash,'hand_landmarker.task']]){
 const bytes=await readFile(path);if(bytes.length>12_000_000||sha(bytes)!==hash)throw new Error(`${key} model size/hash mismatch`);
 await copyFile(path,resolve(root,name));assets[key]={url:`./assets/${name}`,sha256:hash};
}
// Non-SIMD CPU fallback deliberately chosen for broad compatibility. Exact published SDK0.10.32 bytes.
for(const [key,name,expected] of [
 ['wasmLoader','vision_wasm_nosimd_internal.js','9f8fc960e363f0fb2f42f7937b97ae9cf9a5630490f71031fa90caa9bb121938'],
 ['wasmBinary','vision_wasm_nosimd_internal.wasm','924274fcd5ac8985f6570a8573e7971b7bd2d580ba1b8f3beb0ba8f95db6347c']
]){
 const path=resolve(sdk,'wasm',name),bytes=await readFile(path);if(sha(bytes)!==expected)throw new Error('Unexpected SDK distribution bytes');
 await copyFile(path,resolve(root,name));assets[key]={url:`./assets/${name}`,sha256:expected};
}
await writeFile(resolve(root,'vision-assets.json'),JSON.stringify(assets,null,2)+'\n');
await writeFile(resolve(root,'MODEL_LICENSE_REVIEW.txt'),review);
console.log('Prepared local verified assets. Not camera/hardware acceptance. Preserve model license/notice files required by your review.');
