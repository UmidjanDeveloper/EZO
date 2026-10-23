import { describe, expect, it } from "vitest";
import { normalize, parseIntent } from "./intents";

describe("parseIntent", () => {
  it.each([
    ["Kalkulyatorni och", "calculator"],
    ["kalkulyatorni ochib ber", "calculator"],
    ["Open calculator", "calculator"],
    ["Bloknotni ishga tushir", "notepad"],
    ["Открой калькулятор", "calculator"],
    ["Provodnikni och", "explorer"],
  ])("%s opens a registered app", (input, app) => {
    expect(parseIntent(input)).toEqual({ kind: "open_app", app });
  });

  it.each([
    ["Ovozni balandlat", "up"],
    ["ovozni ko‘tar", "up"],
    ["Ovozni pasaytir", "down"],
    ["Ovozni o‘chir", "mute"],
    ["volume down", "down"],
  ])("%s changes the volume", (input, change) => {
    expect(parseIntent(input)).toEqual({ kind: "volume", change });
  });

  it("finds a file by the words before 'faylini top'", () => {
    expect(parseIntent("Hisobot 2026 faylini top")).toEqual({ kind: "find_file", query: "hisobot 2026" });
    expect(parseIntent("menga \"shartnoma\" nomli hujjatni qidir")).toEqual({
      kind: "find_file",
      query: "shartnoma",
    });
    expect(parseIntent("find file budget")).toEqual({ kind: "find_file", query: "budget" });
  });

  it("opens a file or a numbered search result", () => {
    expect(parseIntent("rezyume faylini och")).toEqual({ kind: "open_file", query: "rezyume" });
    expect(parseIntent("Birinchisini och")).toEqual({ kind: "open_result", index: 0 });
    expect(parseIntent("2 ni och")).toEqual({ kind: "open_result", index: 1 });
  });

  it("dictation keeps the user's own casing and punctuation", () => {
    expect(parseIntent("Yoz: Salom, Bahrom aka! Ertaga uchrashamiz.")).toEqual({
      kind: "dictate",
      text: "Salom, Bahrom aka! Ertaga uchrashamiz.",
    });
    expect(parseIntent("yozib ber - Hisobot tayyor")).toEqual({ kind: "dictate", text: "Hisobot tayyor" });
  });

  it("asks about the screen only when the user mentions it", () => {
    expect(parseIntent("Ekranimda nima bor, tushuntir").kind).toBe("explain_screen");
    expect(parseIntent("Explain my screen").kind).toBe("explain_screen");
  });

  it.each([
    "Bugun ob-havo qanday?",
    "Kalkulyator haqida gapirib ber",
    "rm -rf / ni ishga tushir",
    "powershell Remove-Item C:\\ ochib ber",
    "Yoz:",
  ])("everything else is a conversation: %s", (input) => {
    expect(parseIntent(input).kind).toBe("chat");
  });

  it("normalizes Uzbek apostrophes", () => {
    expect(normalize("  O‘zbek  ʻtiliʼ ")).toBe("o'zbek 'tili'");
  });
});
