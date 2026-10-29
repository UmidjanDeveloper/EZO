/**
 * Runtime configuration for the browser, read from server environment
 * variables on every request. Set EZO_API_URL to point the web app at an API
 * without rebuilding it (used by Docker and the end-to-end tests).
 */
import { apiProxyTarget, publicApiUrl } from "@/lib/runtime-config";

export const dynamic = "force-dynamic";

export function GET() {
  let body: string;
  try {
    body = apiProxyTarget(process.env)
      ? "window.__EZO_API_URL__ = window.location.origin;"
      : `window.__EZO_API_URL__ = ${JSON.stringify(publicApiUrl(process.env))};`;
  } catch {
    return new Response("throw new Error('EZO public API URL is not configured correctly');", {
      status: 503,
      headers: { "Content-Type": "application/javascript; charset=utf-8", "Cache-Control": "no-store" },
    });
  }
  return new Response(body, {
    headers: {
      "Content-Type": "application/javascript; charset=utf-8",
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
    },
  });
}
