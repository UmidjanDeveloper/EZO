import { describe, expect, it } from "vitest";
import { format, STRINGS, strings } from "./strings";

function flatten(value: unknown, prefix = ""): Record<string, string> {
  if (typeof value === "string") return { [prefix]: value };
  const out: Record<string, string> = {};
  for (const [key, child] of Object.entries(value as Record<string, unknown>)) Object.assign(out, flatten(child, prefix ? `${prefix}.${key}` : key));
  return out;
}

describe("mobile strings", () => {
  it("has every key, non-empty, with matching placeholders in uz, en and ru", () => {
    const base = flatten(STRINGS.uz);
    expect(Object.keys(base).length).toBeGreaterThan(150);
    for (const lang of ["en", "ru"] as const) {
      const other = flatten(STRINGS[lang]);
      expect(Object.keys(other).sort()).toEqual(Object.keys(base).sort());
      for (const [key, text] of Object.entries(base)) {
        const holes = (s: string) => (s.match(/\{\w+\}/g) ?? []).sort();
        expect(holes(other[key]!), `${lang}:${key}`).toEqual(holes(text));
        expect(other[key], `${lang}:${key}`).not.toBe("");
      }
    }
  });

  it("formats placeholders and falls back to Uzbek", () => {
    expect(format(strings("en").status.connectedTo, { name: "Umid" })).toBe("Connected: Umid");
    expect(strings("de").nav.chat).toBe("Suhbat");
  });
});
