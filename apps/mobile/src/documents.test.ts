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

  it("never parses PDF and DOCX on the phone (EZO Student's isolated worker does)", () => {
    for (const name of ["shartnoma.pdf", "xat.docx"]) {
      const result = documentPrompt(name, b64("x"));
      expect(result.ok).toBe(false);
      if (!result.ok) expect(result.reason).toContain("PDF/DOCX/EPUB");
    }
  });

  it("decodes base64 as UTF-8", () => {
    expect(decodeBase64Utf8(b64("Салом ўзбек"))).toBe("Салом ўзбек");
  });
});

describe("Student documents on the phone", () => {
  it("routes PDF/DOCX/EPUB and scans to EZO Student, text files stay on the phone", async () => {
    const { isStudentDocument, documentPrompt } = await import("./documents");
    for (const name of ["a.pdf", "b.DOCX", "c.epub", "scan.jpg", "photo.jpeg", "page.png"]) expect(isStudentDocument(name)).toBe(true);
    for (const name of ["notes.txt", "data.csv", "app.exe", "x.xlsx"]) expect(isStudentDocument(name)).toBe(false);
    expect(documentPrompt("app.exe", "eA==").ok).toBe(false);
  });

  it("never invents progress: queued too long says the worker is not running", async () => {
    const { jobMessage } = await import("./documents");
    expect(jobMessage("queued", 5)).toBe("Hujjat navbatda…");
    expect(jobMessage("running", 5)).toBe("Hujjat o‘qilmoqda…");
    expect(jobMessage("queued", 95)).toContain("ishchisi hozir ishlamayapti");
    expect(jobMessage("failed", 0, "OCR could not read this scan")).toContain("OCR could not read this scan");
  });
});
