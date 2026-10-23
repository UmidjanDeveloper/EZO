import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { describe, expect, it } from "vitest";

const EXT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../chrome-extension");
const text = (name: string) => readFileSync(path.join(EXT, name), "utf8");
const manifest = JSON.parse(text("manifest.json")) as Record<string, unknown>;

describe("chrome extension permissions", () => {
  it("has no automatic content-script injection", () => {
    expect(manifest.content_scripts).toBeUndefined();
  });

  it("has no background worker, notifications or persistent hooks", () => {
    expect(manifest.background).toBeUndefined();
    expect(manifest.permissions).not.toContain("notifications");
    expect(manifest.permissions).not.toContain("webRequest");
    expect(manifest.permissions).not.toContain("tabs");
    expect(manifest.permissions).not.toContain("cookies");
  });

  it("requests only activeTab + scripting; no required host access", () => {
    expect([...(manifest.permissions as string[])].sort()).toEqual(["activeTab", "scripting"]);
    expect(manifest.host_permissions).toBeUndefined();
  });

  it("optional host permissions are limited to local backend origins, never all sites", () => {
    const optional = manifest.optional_host_permissions as string[];
    expect(optional).toEqual(["http://localhost/*", "http://127.0.0.1/*"]);
    const everything = JSON.stringify(manifest);
    expect(everything).not.toContain("<all_urls>");
    expect(everything).not.toContain("https://*/*");
    expect(everything).not.toContain("http://*/*");
    expect(everything).not.toContain("*://*/*");
  });

  it("ships no leftover content/background scripts", () => {
    expect(() => text("content.js")).toThrow();
    expect(() => text("background.js")).toThrow();
  });

  it("popup uses only GET /api/health and no JARVIS task endpoints", () => {
    const all = text("popup.js") + text("status.js") + text("popup.html");
    expect(all).toContain("/api/health");
    expect(all).not.toMatch(/\/api\/jarvis/);
    expect(all).not.toMatch(/setInterval|setTimeout/);
    expect(all).not.toMatch(/method:\s*["']POST["']/);
  });

  it("page reading happens inside a click handler", () => {
    const popup = text("popup.js");
    const clickIdx = popup.indexOf('addEventListener("click"', popup.indexOf("readPageBtn"));
    expect(clickIdx).toBeGreaterThan(-1);
    expect(popup.indexOf("executeScript")).toBeGreaterThan(clickIdx);
  });
});

describe("chrome extension status copy", async () => {
  const status = (await import(/* @vite-ignore */ pathToFileURL(path.join(EXT, "status.js")).href)) as {
    describeBackend: (r: unknown) => { state: string; text: string };
    originPattern: (base: string) => string;
    UNAVAILABLE: Record<string, string>;
  };

  it("scopes the permission pattern to one hostname", () => {
    expect(status.originPattern("http://localhost:8000")).toBe("http://localhost/*");
    expect(() => status.originPattern("file:///etc/passwd")).toThrow();
  });

  it("never claims connected/paired from a mere HTTP 200", () => {
    const view = status.describeBackend({ ok: true, status: 200 });
    expect(view.state).toBe("reachable");
    expect(view.text).toMatch(/juftlash degani emas/);
    expect(view.text).not.toMatch(/ulangan|juftlangan/i);
  });

  it("unknown / denied / unreachable are not reported as healthy", () => {
    expect(status.describeBackend(null).state).toBe("unknown");
    expect(status.describeBackend({ ok: false, reason: "permission_denied" }).state).toBe("unknown");
    expect(status.describeBackend({ ok: false, reason: "unreachable" }).state).toBe("unreachable");
  });

  it("unsupported features are stated as not available", () => {
    for (const value of Object.values(status.UNAVAILABLE)) expect(value).toMatch(/mavjud emas|yuborilmaydi/);
  });
});
