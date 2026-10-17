import { describe, expect, it } from "vitest";
import { dictionaries, format } from "./messages";

type Tree = { [key: string]: Tree | string | string[] };

function shape(tree: Tree, prefix = ""): string[] {
  return Object.entries(tree).flatMap(([key, value]) => {
    const path = prefix ? `${prefix}.${key}` : key;
    if (Array.isArray(value)) return [`${path}[${value.length}]`];
    if (typeof value === "string") return [path];
    return shape(value, path);
  });
}

describe("i18n dictionaries", () => {
  it("every language has exactly the same keys and list lengths as Uzbek", () => {
    const reference = shape(dictionaries.uz as unknown as Tree);
    for (const language of ["en", "ru"] as const) {
      expect(shape(dictionaries[language] as unknown as Tree)).toEqual(reference);
    }
  });

  it("no text is empty", () => {
    for (const dictionary of Object.values(dictionaries)) {
      const texts = JSON.stringify(dictionary);
      expect(texts).not.toContain('""');
    }
  });

  it("formats placeholders", () => {
    expect(format("{agent} ({milestone})", { agent: "Coach", milestone: 3 })).toBe("Coach (3)");
    expect(format("{missing}")).toBe("{missing}");
  });
});
