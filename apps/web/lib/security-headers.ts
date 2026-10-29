/**
 * Browser security policy for the EZO web app.
 *
 * The owner's API token lives in this origin's storage, so the policy limits what an
 * injected script could do: scripts run only with this request's nonce (Next.js adds it
 * to its own scripts), the page talks only to itself and the EZO API, loads no third-party
 * resources and cannot be framed.
 */
export function contentSecurityPolicy(nonce: string, apiOrigin: string, dev = false, frameAncestors = "'none'"): string {
  const api = apiOrigin ? ` ${apiOrigin}` : "";
  const directives = [
    "default-src 'self'",
    // blob: lets the clap AudioWorklet load its module (made by the page itself, never fetched).
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic' blob: 'wasm-unsafe-eval'${dev ? " 'unsafe-eval'" : ""}`,
    // React sets style attributes (animations, sizes); styles cannot run code.
    "style-src 'self' 'unsafe-inline'",
    `img-src 'self' blob: data:${api}`,
    `media-src 'self' blob:${api}`,
    `connect-src 'self'${api}${dev ? " ws: wss:" : ""}`,
    "worker-src 'self' blob:",
    "font-src 'self' data:",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    `frame-ancestors ${frameAncestors}`,
  ];
  if (apiOrigin.startsWith("https://")) directives.push("upgrade-insecure-requests");
  return directives.join("; ");
}

export const STATIC_SECURITY_HEADERS: Readonly<Record<string, string>> = {
  "X-Frame-Options": "DENY",
  "X-Content-Type-Options": "nosniff",
  "Referrer-Policy": "no-referrer",
  // Device access stays same-origin, and camera capture additionally requires an explicit click.
  "Permissions-Policy": "camera=(self), geolocation=(), payment=(), usb=(), microphone=(self)",
};

/** Explicit, deployment-opt-in embedding for a trusted preview; production defaults stay deny-all. */
export function previewFrameAncestors(value: string | undefined): string | null {
  if (!value) return null;
  const origins = value.trim().split(/[\s,]+/);
  if (!origins.length || origins.some((origin) => !/^https:\/\/[a-zA-Z0-9.*-]+(?::\d+)?$/.test(origin) || origin.includes(";") || origin.includes("'"))) return null;
  return origins.join(" ");
}
