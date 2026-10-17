import { describe, expect, it } from "vitest";
import { titleFrom } from "./MessageBubble";

describe("titleFrom", () => {
  it("uses the first heading or line without Markdown", () => {
    expect(titleFrom("## **Biznes reja** 2026\n\nMatn")).toBe("Biznes reja 2026");
    expect(titleFrom("\n\n- birinchi band\n- ikkinchi")).toBe("birinchi band");
    expect(titleFrom("1. Qadam bir")).toBe("Qadam bir");
  });

  it("shortens long titles and never returns an empty one", () => {
    expect(titleFrom("a".repeat(120))).toHaveLength(78);
    expect(titleFrom("   ")).toBe("EZO");
  });
});
