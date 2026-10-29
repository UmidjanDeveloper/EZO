import { test, expect } from "@playwright/test";

const API_PORT = Number(process.env.E2E_API_PORT ?? 8100);

test("the deployed browser discovers its public API without receiving server secrets", async ({ page }) => {
  const response = await page.request.get("/ezo-config");
  expect(response.status()).toBe(200);
  expect(response.headers()["cache-control"]).toBe("no-store");
  const source = await response.text();
  expect(source).toBe(`window.__EZO_API_URL__ = "http://localhost:${API_PORT}";`);
  await page.goto("/");
  expect(await page.evaluate(() => (window as Window & { __EZO_API_URL__?: string }).__EZO_API_URL__))
    .toBe(`http://localhost:${API_PORT}`);
  await expect(page.locator("body")).toBeVisible();
});

test("every page runs under a nonce content security policy without violations", async ({ page }) => {
  const violations: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error" && /Content Security Policy/i.test(message.text())) violations.push(message.text());
  });
  await page.addInitScript(() => {
    document.addEventListener("securitypolicyviolation", (event) => {
      console.error(`Content Security Policy violation: ${event.violatedDirective} ${event.blockedURI}`);
    });
  });
  const response = await page.goto("/");
  const headers = response?.headers() ?? {};
  const csp = headers["content-security-policy"] ?? "";
  expect(csp).toMatch(/script-src 'self' 'nonce-[^']+' 'strict-dynamic'/);
  expect(csp).toContain(`connect-src 'self' http://localhost:${API_PORT}`);
  expect(csp).toContain("frame-ancestors 'none'");
  expect(headers["x-frame-options"]).toBe("DENY");
  // The inline theme script and /ezo-config only run because they carry the nonce.
  expect(await page.evaluate(() => (window as Window & { __EZO_API_URL__?: string }).__EZO_API_URL__))
    .toBe(`http://localhost:${API_PORT}`);
  for (const path of ["/knowledge", "/settings", "/memory", "/projects", "/artifacts", "/translate", "/language"]) {
    await page.goto(path);
    await expect(page.locator("main").first()).toBeVisible();
  }
  expect(violations).toEqual([]);
});
