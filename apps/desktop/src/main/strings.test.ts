import { describe, expect, it } from "vitest";
import { format, STRINGS, strings, UI_LANGUAGES } from "./strings";

function flatten(value: unknown, prefix = ""): Record<string, string> {
  if (typeof value === "string") return { [prefix]: value };
  const out: Record<string, string> = {};
  for (const [key, child] of Object.entries(value as Record<string, unknown>)) {
    Object.assign(out, flatten(child, prefix ? `${prefix}.${key}` : key));
  }
  return out;
}

describe("desktop strings", () => {
  it("has every key in all three languages with the same placeholders", () => {
    const base = flatten(STRINGS.uz);
    expect(Object.keys(base).length).toBeGreaterThan(100);
    for (const lang of ["en", "ru"] as const) {
      const other = flatten(STRINGS[lang]);
      expect(Object.keys(other).sort()).toEqual(Object.keys(base).sort());
      for (const [key, text] of Object.entries(base)) {
        const placeholders = (s: string) => (s.match(/\{\w+\}/g) ?? []).sort();
        expect(placeholders(other[key]!), `${lang}:${key}`).toEqual(placeholders(text));
        if (text) expect(other[key], `${lang}:${key}`).not.toBe("");
      }
    }
  });

  it("formats placeholders and leaves unknown ones visible", () => {
    expect(format("{shortcut} — gapiring", { shortcut: "Ctrl+Alt+Space" })).toBe("Ctrl+Alt+Space — gapiring");
    expect(format("Kod: {code}", {})).toBe("Kod: {code}");
  });

  it("falls back to Uzbek for an unknown language and lists the three UI languages", () => {
    expect(strings("xx" as "uz").pill.idle).toBe("EZO");
    expect(UI_LANGUAGES.map((l) => l.code)).toEqual(["uz", "en", "ru"]);
  });
});
