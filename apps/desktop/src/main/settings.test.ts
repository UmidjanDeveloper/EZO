import { describe, expect, it } from "vitest";
import { sanitizeSettings } from "./settings";

describe("sanitizeSettings", () => {
  it("keeps a chosen UI language and falls back to Uzbek for anything else", () => {
    expect(sanitizeSettings({ language: "ru" }).language).toBe("ru");
    expect(sanitizeSettings({ language: "en" }).language).toBe("en");
    expect(sanitizeSettings({ language: "de" }).language).toBe("uz");
    expect(sanitizeSettings({}).language).toBe("uz");
  });

  it("accepts only https or private http servers", () => {
    expect(sanitizeSettings({ apiUrl: "http://192.168.1.20:8000/" }).apiUrl).toBe("http://192.168.1.20:8000");
    expect(sanitizeSettings({ apiUrl: "http://evil.example" }).apiUrl).toBe("http://localhost:8000");
  });
});
