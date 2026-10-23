import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const dir = join(__dirname, "..", "..", "chrome-extension");
const manifest = JSON.parse(readFileSync(join(dir, "manifest.json"), "utf8"));
const popup = readFileSync(join(dir, "popup.js"), "utf8");

describe("Chrome extension contract", () => {
  it("never injects into web pages or requests broad host access", () => {
    expect(manifest.content_scripts).toBeUndefined();
    expect(manifest.host_permissions).toBeUndefined();
    expect(manifest.optional_host_permissions).toBeUndefined();
    expect(manifest.permissions).toEqual(["storage"]);
  });

  it("calls only the existing authenticated capabilities route", () => {
    const routes = [...popup.matchAll(/\/api\/[a-z/_-]+/g)].map((m) => m[0]);
    expect(new Set(routes)).toEqual(new Set(["/api/jarvis/capabilities"]));
    expect(popup).toContain("Authorization");
  });
});
