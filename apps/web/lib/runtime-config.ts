/** Only this public origin crosses the server/browser boundary. Never send tokens or keys. */
export function publicApiUrl(env: Readonly<Record<string, string | undefined>>): string {
  const value = env.EZO_API_URL ?? env.NEXT_PUBLIC_API_URL;
  if (!value) {
    if (env.NODE_ENV === "production") throw new Error("EZO_API_URL must be configured");
    return "http://localhost:8000";
  }
  const url = new URL(value);
  const loopback = ["localhost", "127.0.0.1", "[::1]"].includes(url.hostname);
  if (
    (url.protocol !== "https:" && !(url.protocol === "http:" && loopback)) ||
    url.username || url.password || url.search || url.hash || url.pathname !== "/"
  ) throw new Error("EZO_API_URL must be an HTTPS origin (HTTP loopback is supported locally)");
  return url.origin;
}
