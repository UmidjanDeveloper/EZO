import { describe, expect, it } from "vitest";
import { toSpeakableText } from "./speech";

describe("toSpeakableText", () => {
  it("removes Markdown, code, links and emoji so the reply sounds natural", () => {
    const markdown = [
      "## Reja",
      "- **Birinchi**: [sayt](https://example.com) oching",
      "1. `npm install` qiling",
      "```bash\nrm -rf /\n```",
      "Tayyor! 🎉",
    ].join("\n");
    expect(toSpeakableText(markdown)).toBe("Reja Birinchi: sayt oching npm install qiling Tayyor!");
  });

  it("removes underscore emphasis but keeps names with underscores", () => {
    expect(toSpeakableText("_Muhim_: ANTHROPIC_API_KEY ni yozing")).toBe("Muhim: ANTHROPIC_API_KEY ni yozing");
  });

  it("keeps plain sentences unchanged", () => {
    expect(toSpeakableText("Salom! Qalaysiz?")).toBe("Salom! Qalaysiz?");
  });
});
