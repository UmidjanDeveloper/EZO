import { describe, expect, it } from "vitest";
import { contentSecurityPolicy, STATIC_SECURITY_HEADERS } from "./security-headers";

describe("content security policy", () => {
  it("allows only nonce scripts and the EZO API, and forbids framing", () => {
    const csp = contentSecurityPolicy("abc", "https://api.ezo.example");
    expect(csp).toContain("script-src 'self' 'nonce-abc' 'strict-dynamic' 'wasm-unsafe-eval' blob:");
    expect(csp).not.toContain("'unsafe-eval'"); // WASM may compile; JavaScript eval stays forbidden
    expect(csp).toContain("worker-src 'self' blob:"); // the perception worker from this origin
    expect(STATIC_SECURITY_HEADERS["Permissions-Policy"]).toContain("camera=(self)");
    expect(csp).toContain("connect-src 'self' blob: https://api.ezo.example");
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
