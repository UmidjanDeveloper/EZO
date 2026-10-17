import { describe, expect, it } from "vitest";
import { bandText } from "./LanguagePage";

describe("bandText", () => {
  it("shows a single band or a range, and nothing when not assessed", () => {
    expect(bandText(6, 6)).toBe("6");
    expect(bandText(5.5, 6.5)).toBe("5.5–6.5");
    expect(bandText(null, null)).toBeNull();
    expect(bandText(6, null)).toBeNull();
  });
});
