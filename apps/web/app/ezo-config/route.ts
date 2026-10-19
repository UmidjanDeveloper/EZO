/**
 * Runtime configuration for the browser, read from server environment
 * variables on every request. Set EZO_API_URL to point the web app at an API
 * without rebuilding it (used by Docker and the end-to-end tests).
 */
import { publicApiUrl } from "@/lib/runtime-config";

export const dynamic = "force-dynamic";

export function GET() {
  let apiUrl: string;
  try {
    apiUrl = publicApiUrl(process.env);
  } catch {
    return new Response("throw new Error('EZO public API URL is not configured correctly');", {
      status: 503,
      headers: { "Content-Type": "application/javascript; charset=utf-8", "Cache-Control": "no-store" },
    });
  }
  const body = `window.__EZO_API_URL__ = ${JSON.stringify(apiUrl)};`;
  return new Response(body, {
    headers: {
      "Content-Type": "application/javascript; charset=utf-8",
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
    },
  });
}
