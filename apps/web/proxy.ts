import { NextResponse, type NextRequest } from "next/server";
import { apiProxyTarget, publicApiUrl } from "@/lib/runtime-config";
import { contentSecurityPolicy, previewFrameAncestors, STATIC_SECURITY_HEADERS } from "@/lib/security-headers";

/** Adds a per-request nonce and the security headers (CSP, framing, referrer). */
export function proxy(request: NextRequest) {
  const nonce = btoa(crypto.randomUUID());
  let apiOrigin = "";
  try {
    apiOrigin = apiProxyTarget(process.env) ? "" : publicApiUrl(process.env);
  } catch {
    apiOrigin = ""; // /ezo-config reports the misconfiguration; the page stays locked down
  }
  const ancestors = previewFrameAncestors(process.env.EZO_PREVIEW_ORIGINS);
  const policy = contentSecurityPolicy(nonce, apiOrigin, process.env.NODE_ENV === "development", ancestors ?? undefined);
  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-nonce", nonce);
  requestHeaders.set("Content-Security-Policy", policy);
  const response = NextResponse.next({ request: { headers: requestHeaders } });
  response.headers.set("Content-Security-Policy", policy);
  for (const [name, value] of Object.entries(STATIC_SECURITY_HEADERS)) {
    if (ancestors && name === "X-Frame-Options") continue;
    response.headers.set(name, value);
  }
  return response;
}

export const config = {
  matcher: [
    {
      source: "/((?!_next/static|_next/image|favicon.ico).*)",
      missing: [
        { type: "header", key: "next-router-prefetch" },
        { type: "header", key: "purpose", value: "prefetch" },
      ],
    },
  ],
};
