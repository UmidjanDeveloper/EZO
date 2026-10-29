/** Additive light only. No skin, eyes, mouth, character material or imported model. */
export const ENERGY_VERTEX = /* glsl */ `
precision highp float;
attribute vec3 aPos;
attribute vec4 aData;
attribute vec2 aExtra;
uniform mat4 uVP;
uniform float uTime, uLevel, uEnergy, uWarmth, uListen, uThink, uSpeak, uError, uWork, uSuccess, uOffline;
uniform float uYaw, uPitch, uPx, uGlowPx, uRef, uGlow, uIntensity;
varying vec3 vColor;
varying float vAlpha;
const vec3 CYAN = vec3(0.08, 0.78, 1.0);
const vec3 ICE = vec3(0.62, 0.96, 1.0);
const vec3 AMBER = vec3(1.0, 0.34, 0.035);
const vec3 GOLD = vec3(1.0, 0.72, 0.24);
vec3 orient(vec3 p) {
  p.y -= 0.12;
  float c = cos(uYaw), s = sin(uYaw);
  p = vec3(c*p.x+s*p.z,p.y,-s*p.x+c*p.z);
  c = cos(uPitch); s = sin(uPitch);
  p = vec3(p.x,c*p.y-s*p.z,s*p.y+c*p.z);
  p.y += 0.12;
  return p;
}
void main() {
  float kind=aData.x, seed=aData.y, bright=aData.z, warm=aData.w;
  float t=uTime;
  vec3 p=aPos;
  vec3 color=CYAN;
  float alpha=0.6, size=1.8;
  // Incommensurate frequencies avoid a short, robotic loop.
  float breath=(sin(t*0.71)+0.45*sin(t*1.13+1.7))*0.0035;
  float scan=exp(-pow((p.y-(1.4-fract(t*(0.12+uWork*0.16))*3.3))*7.0,2.0))*uThink;
  float voice=uLevel*uSpeak;
  float listenPulse=uListen*(0.5+0.5*sin(t*2.1))*(0.2+uLevel*0.8);
  if(kind<0.5) {
    float front=smoothstep(-0.05,0.5,aExtra.y);
    float reorganize=sin(p.y*72.0+t*1.6+sin(p.x*13.0+t*0.4))*uThink;
    p.y+=breath+warm*(voice*0.018*sin(p.x*19.0+t*5.0)+reorganize*0.006);
    p.x+=sin(p.y*15.0+t*0.47)*0.0025;
    float rim=1.0-abs(aExtra.y);
    color=mix(mix(CYAN,ICE,rim*0.65+scan*0.4),mix(AMBER,GOLD,0.32+voice*0.55),warm*uWarmth);
    alpha=bright*(0.25+front*0.52+rim*rim*0.35+warm*uWarmth*0.85+scan*0.3);
    alpha*=smoothstep(-0.045,0.095,aPos.y);
    size=1.9+warm*0.65+voice*0.5;
  } else if(kind<1.5) {
    p.y+=breath;
    p.x+=sin(p.y*8.0+t*0.37)*0.002;
    float rim=1.0-abs(aExtra.y);
    color=mix(CYAN,ICE,rim*0.5+scan*0.4);
    alpha=bright*(0.48+rim*rim*0.48)+scan*0.3+listenPulse*0.12;
    size=1.65;
  } else if(kind<2.5) {
    p.y+=breath;
    p.x+=aExtra.x*(0.002+0.003*sin(t*0.8+p.y*9.0));
    color=mix(CYAN,ICE,0.5);
    alpha=bright*(0.65+listenPulse*0.3+scan*0.3);
    size=2.0;
  } else if(kind<3.5) {
    float life=fract(seed*7.0+t*(0.018+seed*0.016));
    p.xy+=aExtra*(life*0.32)*(1.0-uListen*0.55);
    p.x+=sin(t*0.37+seed*41.0)*0.045;
    p.y+=sin(t*0.23+seed*17.0)*0.06;
    vec2 d=p.xy-vec2(0.0,0.5);
    float a=uThink*sin(t*0.17+seed*3.0)*0.08;
    p.xy=vec2(0.0,0.5)+vec2(cos(a)*d.x-sin(a)*d.y,sin(a)*d.x+cos(a)*d.y);
    color=mix(CYAN,GOLD,warm);
    alpha=bright*sin(life*3.14159)*0.58;
    size=1.0+seed*1.6;
  } else if(kind<4.5) {
    p.y+=breath;
    p.x+=sin(aExtra.x*12.0+t*0.7+aExtra.y*20.0)*0.007;
    float pulse=pow(0.5+0.5*sin(aExtra.x*13.0-t*(1.1+uWork)+aExtra.y*30.0),7.0);
    color=mix(CYAN,GOLD,warm);
    alpha=bright*(0.22+pulse*0.65+listenPulse*0.2);
    size=1.45+pulse*0.8;
  } else if(kind<5.5) {
    p.y+=breath;
    color=mix(AMBER,GOLD,0.18+voice*0.65);
    alpha=bright*warm*uWarmth*(0.035+voice*0.065);
    size=15.0+bright*12.0+voice*8.0;
  } else if(kind<6.5) {
    float flow=aExtra.x;
    p.y+=sin(flow*8.0-t*0.45+aExtra.y*4.0)*0.13+sin(flow*17.0+t*0.29)*0.045;
    p.y*=1.0-uThink*0.16;
    p.x*=1.0-uThink*0.12;
    p.z+=uThink*0.2;
    float pulse=0.6+0.4*sin(flow*12.0-t*0.7+aExtra.y*8.0);
    color=mix(CYAN,GOLD,warm);
    alpha=bright*(0.62+pulse*0.48+voice*0.25);
    size=2.0+warm*0.6;
  } else {
    p.y+=breath;
    color=mix(ICE,GOLD,0.4+uWork*0.4);
    alpha=bright*(0.5+listenPulse*0.3+uWork*0.25);
    size=2.0;
  }
  if(kind<2.5 || (kind>3.5 && kind<5.5) || kind>6.5) p=orient(p);
  float burst=uSuccess*exp(-pow((length(p.xy-vec2(0.0,-0.6))-fract(t*0.3)*2.0)*7.0,2.0));
  color=mix(color,GOLD,burst*0.65);
  color=mix(color,vec3(1.0,0.24,0.12),uError*0.7);
  color=mix(color,vec3(0.24,0.38,0.43),uOffline*0.85);
  alpha=(alpha+burst*0.3)*(1.0-uOffline*0.62)*uIntensity;
  vec4 clip=uVP*vec4(p,1.0);
  gl_Position=clip;
  float px=(kind>4.5 && kind<5.5)?uGlowPx:uPx;
  gl_PointSize=clamp(size*px*(uRef/clip.w),1.0,64.0);
  vColor=color;
  vAlpha=clamp(alpha,0.0,1.0);
  if(uGlow>0.5) {
    if(seed>0.18 || (kind>4.5 && kind<5.5)) {
      gl_Position=vec4(2.0,2.0,2.0,1.0); gl_PointSize=1.0;
    } else { gl_PointSize=min(40.0,gl_PointSize*4.0); vAlpha*=0.12; }
  }
}
`;
export const ENERGY_FRAGMENT = /* glsl */ `
precision mediump float;
varying vec3 vColor;
varying float vAlpha;
void main() {
  vec2 p=gl_PointCoord*2.0-1.0;
  float d=dot(p,p);
  if(d>1.0) discard;
  float light=exp(-d*3.8)*(1.0-smoothstep(0.6,1.0,d));
  gl_FragColor=vec4(vColor*light*vAlpha,light*vAlpha);
}
`;
