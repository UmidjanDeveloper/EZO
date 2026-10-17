/**
 * Runtime configuration for the browser, read from server environment
 * variables on every request. Set EZO_API_URL to point the web app at an API
 * without rebuilding it (used by Docker and the end-to-end tests).
 */
export const dynamic = "force-dynamic";

export function GET() {
  const apiUrl = process.env.EZO_API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  const body = `window.__EZO_API_URL__ = ${JSON.stringify(apiUrl)};`;
  return new Response(body, {
    headers: {
      "Content-Type": "application/javascript; charset=utf-8",
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
    },
  });
}
