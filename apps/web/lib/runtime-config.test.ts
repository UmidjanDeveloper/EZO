import { describe, expect, it } from "vitest";
import { apiProxyTarget, publicApiUrl } from "./runtime-config";

describe("public API runtime configuration", () => {
  it("exposes only the API origin, with runtime configuration taking precedence", () => {
    expect(publicApiUrl({
      NODE_ENV: "production", EZO_API_URL: "https://api.example.com/",
      NEXT_PUBLIC_API_URL: "https://old.example.com", ANTHROPIC_API_KEY: "server-only",
    })).toBe("https://api.example.com");
  });

  it("requires an explicit endpoint in production and keeps local development working", () => {
    expect(() => publicApiUrl({ NODE_ENV: "production" })).toThrow();
    expect(publicApiUrl({ NODE_ENV: "development" })).toBe("http://localhost:8000");
    expect(publicApiUrl({ NODE_ENV: "production", EZO_API_URL: "http://localhost:8100" }))
      .toBe("http://localhost:8100");
  });

  it.each([
    "http://api.example.com", "https://user:password@api.example.com", "javascript:alert(1)",
    "https://api.example.com/path", "https://api.example.com?key=secret", "not-a-url",
  ])("rejects unsafe endpoint %s", (value) => {
    expect(() => publicApiUrl({ EZO_API_URL: value })).toThrow();
  });
});

describe("preview API proxy", () => {
  it("is opt-in and loopback-only", () => {
    expect(apiProxyTarget({})).toBeNull();
    expect(apiProxyTarget({ EZO_API_PROXY_TARGET: "http://127.0.0.1:8100/" })).toBe("http://127.0.0.1:8100");
    expect(() => apiProxyTarget({ EZO_API_PROXY_TARGET: "https://api.example.com" })).toThrow();
    expect(() => apiProxyTarget({ EZO_API_PROXY_TARGET: "http://10.0.0.1:8100" })).toThrow();
  });
});
