import { describe, expect, it } from "vitest";
import { contentSecurityPolicy, previewFrameAncestors, STATIC_SECURITY_HEADERS } from "./security-headers";

describe("content security policy", () => {
  it("allows only nonce scripts and the EZO API, and forbids framing", () => {
    const csp = contentSecurityPolicy("abc", "https://api.ezo.example");
    expect(csp).toContain("script-src 'self' 'nonce-abc' 'strict-dynamic' blob:"); // blob: for the clap AudioWorklet
    expect(csp).not.toContain("'unsafe-eval'");
    expect(csp).toContain("'wasm-unsafe-eval'");
    expect(csp).toContain("worker-src 'self' blob:");
    expect(STATIC_SECURITY_HEADERS["Permissions-Policy"]).toContain("camera=(self)");
    expect(csp).toContain("connect-src 'self' https://api.ezo.example");
    expect(csp).toContain("frame-ancestors 'none'");
    expect(csp).toContain("object-src 'none'");
    expect(csp).toContain("upgrade-insecure-requests");
    expect(STATIC_SECURITY_HEADERS["X-Frame-Options"]).toBe("DENY");
  });

  it("keeps a local HTTP API working and allows hot reload only in development", () => {
    const local = contentSecurityPolicy("n", "http://localhost:8000");
    expect(local).not.toContain("upgrade-insecure-requests");
    expect(contentSecurityPolicy("n", "http://localhost:8000", true)).toContain("'unsafe-eval'");
  });
});

describe("trusted preview embedding", () => {
  it("is explicit and does not change the production default", () => {
    expect(previewFrameAncestors(undefined)).toBeNull();
    expect(previewFrameAncestors("https://arena.ai,https://*.e2b.app")).toBe("https://arena.ai https://*.e2b.app");
    expect(previewFrameAncestors("https://evil.test; script-src *")).toBeNull();
    expect(contentSecurityPolicy("n", "https://api.test")).toContain("frame-ancestors 'none'");
  });
});
