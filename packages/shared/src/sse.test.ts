import { describe, expect, it } from "vitest";
import { SseParser } from "./sse";

describe("SseParser", () => {
  it("parses complete events", () => {
    const parser = new SseParser();
    const events = parser.push('event: meta\ndata: {"a":1}\n\nevent: delta\ndata: {"text":"hi"}\n\n');
    expect(events).toEqual([
      { event: "meta", data: '{"a":1}' },
      { event: "delta", data: '{"text":"hi"}' },
    ]);
  });

  it("buffers events split across chunks", () => {
    const parser = new SseParser();
    expect(parser.push("event: delta\nda")).toEqual([]);
    expect(parser.push('ta: {"text":"Sa')).toEqual([]);
    expect(parser.push('lom"}\n\n')).toEqual([{ event: "delta", data: '{"text":"Salom"}' }]);
  });

  it("handles CRLF, comments and multi-line data", () => {
    const parser = new SseParser();
    const events = parser.push(": keep-alive\r\n\r\nevent: x\r\ndata: a\r\ndata: b\r\n\r\n");
    expect(events).toEqual([{ event: "x", data: "a\nb" }]);
  });

  it("flushes a trailing event without blank line", () => {
    const parser = new SseParser();
    parser.push("event: done\ndata: {}");
    expect(parser.flush()).toEqual([{ event: "done", data: "{}" }]);
  });
});
