import { describe, expect, it } from "vitest";
import { otherSide, parseInterpreterCommand, speakerSide } from "./interpreter";

describe("spoken interpreter command", () => {
  it("starts on the owner's Uzbek phrase, Uzbek ⇄ English by default", () => {
    expect(parseInterpreterCommand("EZO, menga tarjimon bo‘lib ber", "uz")).toEqual({ kind: "start", pair: ["uz", "en"] });
    expect(parseInterpreterCommand("Ezo menga tarjimon bo'lib ber")).toEqual({ kind: "start", pair: ["uz", "en"] });
  });

  it("takes the languages that were named", () => {
    expect(parseInterpreterCommand("rus tili bilan o'zbek tili o'rtasida tarjimon bo'l", "uz")).toEqual({ kind: "start", pair: ["ru", "uz"] });
    expect(parseInterpreterCommand("inglizcha tarjimon bo'lib ber", "uz")).toEqual({ kind: "start", pair: ["uz", "en"] });
    expect(parseInterpreterCommand("ruscha tarjimon kerak", "uz")).toEqual({ kind: "start", pair: ["uz", "ru"] });
    expect(parseInterpreterCommand("be my interpreter between English and Russian", "en")).toEqual({ kind: "start", pair: ["en", "ru"] });
    expect(parseInterpreterCommand("будь переводчиком", "ru")).toEqual({ kind: "start", pair: ["ru", "en"] });
  });

  it("stops on a clear stop phrase", () => {
    expect(parseInterpreterCommand("tarjimon rejimini to'xtat")).toEqual({ kind: "stop" });
    expect(parseInterpreterCommand("tarjimonlik yetarli")).toEqual({ kind: "stop" });
    expect(parseInterpreterCommand("stop interpreting")).toEqual({ kind: "stop" });
    expect(parseInterpreterCommand("хватит переводить")).toEqual({ kind: "stop" });
  });

  it("ignores ordinary speech, including a request to translate one text", () => {
    expect(parseInterpreterCommand("bugun ob-havo qanday")).toBeNull();
    expect(parseInterpreterCommand("bu gapni inglizchaga tarjima qil")).toBeNull();
    expect(parseInterpreterCommand("How are you doing today?")).toBeNull();
  });
});

describe("turn direction", () => {
  it("translates into the other side and trusts the recogniser only within the pair", () => {
    expect(otherSide(["uz", "en"], "uz")).toBe("en");
    expect(otherSide(["uz", "en"], "en")).toBe("uz");
    expect(speakerSide(["uz", "en"], "en", "uz")).toBe("en");
    expect(speakerSide(["uz", "en"], "ru", "uz")).toBe("uz");
    expect(speakerSide(["uz", "en"], null, "en")).toBe("en");
  });
});
