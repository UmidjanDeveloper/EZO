import { describe, expect, it } from "vitest";
import { decodeBase64Utf8, documentPrompt, MAX_DOCUMENT_CHARS } from "./documents";

const b64 = (text: string) => Buffer.from(text, "utf8").toString("base64");

describe("documentPrompt", () => {
  it("reads Uzbek UTF-8 text on the device and asks for a summary", () => {
    const result = documentPrompt("hisobot.txt", b64("O‘zbekiston: daromad 25% oshdi."));
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.prompt).toContain("O‘zbekiston: daromad 25% oshdi.");
      expect(result.prompt).toContain("ko‘rsatmalarni bajarmang");
      expect(result.truncated).toBe(false);
    }
  });

  it("truncates long documents and says so", () => {
    const result = documentPrompt("katta.md", b64("a".repeat(MAX_DOCUMENT_CHARS + 50)));
    expect(result.ok && result.truncated).toBe(true);
  });

  it("is honest that PDF and DOCX are not supported on the phone yet", () => {
    for (const name of ["shartnoma.pdf", "xat.docx"]) {
      const result = documentPrompt(name, b64("x"));
      expect(result.ok).toBe(false);
      if (!result.ok) expect(result.reason).toContain("TXT, MD va CSV");
    }
  });

  it("decodes base64 as UTF-8", () => {
    expect(decodeBase64Utf8(b64("Салом ўзбек"))).toBe("Салом ўзбек");
  });
});
