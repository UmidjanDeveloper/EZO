/** Column-major 4×4 matrices, just what the avatar camera needs. */
export type Mat4 = Float32Array;

export function perspective(fovY: number, aspect: number, near: number, far: number): Mat4 {
  const f = 1 / Math.tan(fovY / 2);
  const nf = 1 / (near - far);
  // prettier-ignore
  return new Float32Array([
    f / aspect, 0, 0, 0,
    0, f, 0, 0,
    0, 0, (far + near) * nf, -1,
    0, 0, 2 * far * near * nf, 0,
  ]);
}

type Vec3 = readonly [number, number, number];

export function lookAt(eye: Vec3, target: Vec3, up: Vec3 = [0, 1, 0]): Mat4 {
  let zx = eye[0] - target[0];
  let zy = eye[1] - target[1];
  let zz = eye[2] - target[2];
  let len = Math.hypot(zx, zy, zz) || 1;
  zx /= len; zy /= len; zz /= len;
  let xx = up[1] * zz - up[2] * zy;
  let xy = up[2] * zx - up[0] * zz;
  let xz = up[0] * zy - up[1] * zx;
  len = Math.hypot(xx, xy, xz) || 1;
  xx /= len; xy /= len; xz /= len;
  const yx = zy * xz - zz * xy;
  const yy = zz * xx - zx * xz;
  const yz = zx * xy - zy * xx;
  // prettier-ignore
  return new Float32Array([
    xx, yx, zx, 0,
    xy, yy, zy, 0,
    xz, yz, zz, 0,
    -(xx * eye[0] + xy * eye[1] + xz * eye[2]),
    -(yx * eye[0] + yy * eye[1] + yz * eye[2]),
    -(zx * eye[0] + zy * eye[1] + zz * eye[2]),
    1,
  ]);
}

export function multiply(a: Mat4, b: Mat4): Mat4 {
  const out = new Float32Array(16);
  for (let col = 0; col < 4; col++) {
    for (let row = 0; row < 4; row++) {
      let sum = 0;
      for (let k = 0; k < 4; k++) sum += a[k * 4 + row]! * b[col * 4 + k]!;
      out[col * 4 + row] = sum;
    }
  }
  return out;
}

/** Projects a point to normalised device coordinates (x, y in -1..1 when visible) and depth w. */
export function project(m: Mat4, x: number, y: number, z: number): [number, number, number] {
  const cx = m[0]! * x + m[4]! * y + m[8]! * z + m[12]!;
  const cy = m[1]! * x + m[5]! * y + m[9]! * z + m[13]!;
  const cw = m[3]! * x + m[7]! * y + m[11]! * z + m[15]!;
  return [cx / cw, cy / cw, cw];
}

export type Framing = "bust" | "head";

export interface Camera {
  viewProjection: Mat4;
  distance: number;
}

const FOV = (40 * Math.PI) / 180;

/**
 * Frames the figure: "bust" shows the head and shoulders (the main stage),
 * "head" fills a small view with the face (the desktop pill).
 */
export function frameCamera(framing: Framing, aspect: number): Camera {
  const [top, bottom, halfWidth] = framing === "head" ? [1.5, -0.25, 0.75] : [1.55, -1.75, 1.2];
  const centerY = (top + bottom) / 2;
  const tan = Math.tan(FOV / 2);
  const fitHeight = (top - bottom) / 2 / tan;
  const fitWidth = halfWidth / (tan * Math.max(aspect, 0.1));
  // Narrow (phone) views may crop the shoulders a little rather than shrink the face.
  const distance = Math.min(Math.max(fitHeight, fitWidth), fitHeight * (framing === "head" ? 1.6 : 1.12));
  const eye = [0, centerY + 0.22, distance] as const;
  const view = lookAt(eye, [0, centerY, 0]);
  return { viewProjection: multiply(perspective(FOV, aspect, 0.1, 40), view), distance };
}
