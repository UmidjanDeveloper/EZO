/**
 * Browser security policy for the EZO web app.
 *
 * The owner's API token lives in this origin's storage, so the policy limits what an
 * injected script could do: scripts run only with this request's nonce (Next.js adds it
 * to its own scripts), the page talks only to itself and the EZO API, loads no third-party
 * resources and cannot be framed.
 */
export function contentSecurityPolicy(nonce: string, apiOrigin: string, dev = false): string {
  const api = apiOrigin ? ` ${apiOrigin}` : "";
  const directives = [
    "default-src 'self'",
    // 'wasm-unsafe-eval': the perception worker compiles the bundled MediaPipe WASM (same origin, SHA256-pinned).
    // blob: lets that worker importScripts its verified loader and the clap AudioWorklet load its module;
    // connect-src blob: lets the WASM runtime read the verified binary blob the worker made itself.
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic' 'wasm-unsafe-eval' blob:${dev ? " 'unsafe-eval'" : ""}`,
    "worker-src 'self' blob:",
    // React sets style attributes (animations, sizes); styles cannot run code.
    "style-src 'self' 'unsafe-inline'",
    `img-src 'self' blob: data:${api}`,
    `media-src 'self' blob:${api}`,
    `connect-src 'self' blob:${api}${dev ? " ws: wss:" : ""}`,
    "font-src 'self' data:",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
  ];
  if (apiOrigin.startsWith("https://")) directives.push("upgrade-insecure-requests");
  return directives.join("; ");
}

export const STATIC_SECURITY_HEADERS: Readonly<Record<string, string>> = {
  "X-Frame-Options": "DENY",
  "X-Content-Type-Options": "nosniff",
  "Referrer-Policy": "no-referrer",
  // The microphone (voice mode, clap) and the camera (attention) are used on this origin only.
  "Permissions-Policy": "camera=(self), geolocation=(), payment=(), usb=(), microphone=(self)",
};
