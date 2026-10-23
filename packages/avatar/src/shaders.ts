/**
 * GLSL ES 1.0 (WebGL 1) so the avatar runs on older phones and in every WebView.
 * All animation is here; the geometry is static (see figure.ts for the point kinds).
 */

const TURN = /* glsl */ `
uniform float uYaw;
uniform float uPitch;
vec3 turn(vec3 p) {
  p.y += 0.4;
  float c = cos(uYaw);
  float s = sin(uYaw);
  p = vec3(c * p.x + s * p.z, p.y, -s * p.x + c * p.z);
  c = cos(uPitch);
  s = sin(uPitch);
  p = vec3(p.x, c * p.y - s * p.z, s * p.y + c * p.z);
  p.y -= 0.4;
  return p;
}
vec3 turnDir(vec3 n) {
  float c = cos(uYaw);
  float s = sin(uYaw);
  return vec3(c * n.x + s * n.z, n.y, -s * n.x + c * n.z);
}
`;

export const POINT_VERTEX = /* glsl */ `
precision highp float;
attribute vec3 aPos;
attribute vec4 aData;
attribute vec2 aExtra;
uniform mat4 uVP;
uniform float uTime;
uniform float uLevel;
uniform float uEnergy;
uniform float uWarmth;
uniform float uListen;
uniform float uThink;
uniform float uSpeak;
uniform float uError;
uniform float uPx;
uniform float uGlowPx;
uniform float uRef;
varying vec3 vColor;
varying float vAlpha;
${TURN}
const vec3 BLUE = vec3(0.12, 0.48, 1.0);
const vec3 CYAN = vec3(0.45, 0.9, 1.0);
const vec3 WARM = vec3(1.0, 0.33, 0.05);
const vec3 GOLD = vec3(1.0, 0.78, 0.32);
const vec3 VIOLET = vec3(0.55, 0.5, 1.0);
const vec3 RED = vec3(1.0, 0.16, 0.2);

void main() {
  float kind = aData.x;
  float seed = aData.y;
  float bright = aData.z;
  float warm = aData.w;
  vec3 p = aPos;
  vec3 col = BLUE;
  float alpha = 0.5;
  float size = 2.0;
  float t = uTime;
  float breath = sin(t * 1.25) * 0.006 * (0.6 + uEnergy);
  float scanY = 1.5 - fract(t * 0.32) * 3.4;
  float scan = uThink * exp(-pow((p.y - scanY) * 7.0, 2.0));

  if (kind < 0.5) {
    // Head contour rings; the face carries the warm voice light and ripples as EZO talks.
    float face = warm;
    float wave = sin(p.x * 22.0 - t * 8.0 + p.y * 30.0) * (0.5 + 0.5 * sin(p.x * 9.0 + t * 2.3));
    p.y += face * (0.003 + 0.045 * uLevel * uSpeak + 0.012 * uLevel * uListen) * wave;
    p.z += face * 0.025 * uLevel * uSpeak * sin(t * 14.0 + p.y * 26.0);
    p.y += breath * 0.5;
    vec3 n = turnDir(vec3(aExtra.x, 0.0, aExtra.y));
    float rim = 1.0 - abs(n.z);
    float w = clamp(face * uWarmth * (0.9 + 0.8 * uLevel), 0.0, 1.0);
    col = mix(mix(BLUE, CYAN, rim * 0.5 + scan), mix(WARM, GOLD, face * face * (0.3 + 0.7 * uLevel)), w);
    alpha = bright * (0.3 + 0.75 * rim * rim) * smoothstep(-0.55, 0.05, n.z) + w * 0.55 + scan * 0.6;
    size = 2.1 + w;
  } else if (kind < 1.5) {
    // Neck rings and chest arcs.
    p.y += breath;
    vec3 n = turnDir(vec3(aExtra.x, 0.0, aExtra.y));
    float rim = 1.0 - abs(n.z);
    col = mix(BLUE, CYAN, 0.25 * bright + scan);
    alpha = bright * (0.38 + 0.6 * rim * rim) + scan * 0.5;
    size = 1.9;
  } else if (kind < 2.5) {
    // Silhouette edge.
    p.y += breath * (p.y < -0.05 ? 1.0 : 0.5);
    col = mix(CYAN, vec3(0.75, 0.97, 1.0), 0.3 + 0.4 * uEnergy);
    alpha = bright * (0.75 + 0.25 * sin(t * 3.0 + seed * 20.0) * uEnergy) + scan * 0.4;
    size = 2.6;
  } else if (kind < 3.5) {
    // Halo: drifts outwards, is drawn in while listening, swirls while thinking.
    float life = fract(t * (0.05 + 0.08 * uEnergy + seed * 0.04) + seed * 13.0);
    float reach = (0.12 + 0.3 * uEnergy) * (1.0 - 1.6 * uListen);
    p.xy += aExtra * life * reach;
    vec2 c = vec2(0.0, 0.62);
    vec2 d = p.xy - c;
    float a = uThink * (t * 0.12 * (0.5 + seed) + sin(t + seed * 6.0) * 0.05);
    p.xy = c + vec2(cos(a) * d.x - sin(a) * d.y, sin(a) * d.x + cos(a) * d.y);
    p.x += sin(t * 1.7 + seed * 30.0) * 0.01;
    alpha = bright * sin(3.14159 * life) * (0.7 + 0.5 * uEnergy);
    col = mix(BLUE, CYAN, seed);
    size = 1.3 + 1.3 * seed;
  } else if (kind < 4.5) {
    // Warm veins with pulses travelling up towards the face.
    p.y += breath;
    float pulse = smoothstep(0.82, 1.0, fract(aExtra.x * 1.4 - t * (0.35 + 0.5 * uEnergy) + seed * 0.05));
    col = mix(WARM, GOLD, pulse);
    alpha = bright * (0.25 + 0.75 * pulse) * (0.45 + 0.55 * uWarmth) + uLevel * uSpeak * 0.25;
    size = 2.2 + pulse * 1.4;
  } else if (kind < 5.5) {
    // Soft glow of the voice light.
    p.x += sin(t * 1.3 + seed * 40.0) * 0.012;
    p.y += cos(t * 1.1 + seed * 30.0) * 0.012 + breath * 0.5;
    col = mix(WARM, GOLD, warm * (0.4 + 0.6 * uLevel));
    alpha = bright * (0.05 + 0.05 * warm) * uWarmth * (0.75 + 0.8 * uLevel);
    size = 12.0 + 16.0 * bright * (0.7 + 0.6 * uLevel);
  } else if (kind < 6.5) {
    // Mountains: twinkling crests, a few warm sparks.
    float twinkle = 0.65 + 0.35 * sin(t * (1.0 + seed * 2.0) + seed * 60.0);
    col = mix(mix(vec3(0.1, 0.35, 0.95), CYAN, bright * 0.6), mix(WARM, GOLD, seed), warm);
    alpha = (bright * 1.1 + warm * 0.8) * twinkle * (0.8 + 0.25 * uLevel);
    size = 3.6 + warm * 1.6;
  } else {
    // Chest light.
    p.y += breath;
    col = mix(CYAN, vec3(1.0), warm);
    alpha = bright * (0.6 + 0.4 * sin(t * 2.2)) * (0.7 + 0.3 * uEnergy);
    size = 2.6 + warm * 3.0;
  }

  if (abs(kind - 6.0) > 0.5) p = turn(p);
  col = mix(col, VIOLET, uThink * 0.18);
  col = mix(col, RED, uError * 0.75);
  vec4 clip = uVP * vec4(p, 1.0);
  gl_Position = clip;
  // Glow sprites scale strictly with the view; lines keep a minimum size in small views.
  float px = (kind > 4.5 && kind < 5.5) ? uGlowPx : uPx;
  gl_PointSize = max(1.0, size * px * (uRef / clip.w));
  vColor = col;
  vAlpha = clamp(alpha, 0.0, 1.0);
}
`;

export const POINT_FRAGMENT = /* glsl */ `
precision mediump float;
varying vec3 vColor;
varying float vAlpha;
void main() {
  vec2 c = gl_PointCoord * 2.0 - 1.0;
  float r2 = dot(c, c);
  if (r2 > 1.0) discard;
  float a = vAlpha * exp(-r2 * 3.2);
  gl_FragColor = vec4(vColor * a, a);
}
`;

/** The filled silhouette only writes depth, hiding the mountains (and the back of the head). */
export const MASK_VERTEX = /* glsl */ `
precision highp float;
attribute vec2 aXY;
uniform mat4 uVP;
${TURN}
void main() {
  gl_Position = uVP * vec4(turn(vec3(aXY, -0.06)), 1.0);
}
`;

export const MASK_FRAGMENT = /* glsl */ `
precision mediump float;
void main() {
  gl_FragColor = vec4(0.0);
}
`;
