import { describe, expect, it } from "vitest";
import { guessLanguage, replies } from "./replies";

describe("replies", () => {
  it("guesses the language of typed commands", () => {
    expect(guessLanguage("Kalkulyatorni och")).toBe("uz");
    expect(guessLanguage("Hisobot faylini top")).toBe("uz");
    expect(guessLanguage("Yoz: Salom")).toBe("uz");
    expect(guessLanguage("Открой калькулятор")).toBe("ru");
    expect(guessLanguage("Калькуляторни оч")).toBe("ru"); // no Uzbek-only letters: ambiguous, Russian
    expect(guessLanguage("Қалайсан")).toBe("uz");
    expect(guessLanguage("Open the calculator")).toBe("en");
    expect(guessLanguage("Turn the volume up")).toBe("en");
    expect(guessLanguage("12345")).toBe("uz");
  });

  it("has every reply in all three languages", () => {
    for (const lang of ["uz", "en", "ru"] as const) {
      const t = replies(lang);
      expect(t.app("calculator").length).toBeGreaterThan(3);
      expect(t.found(2, "1. a\n2. b")).toContain("2");
      expect(Object.keys(t.volume)).toEqual(["up", "down", "mute"]);
    }
    expect(replies("ru").opened(replies("ru").app("notepad"))).toBe("Блокнот открыт.");
  });
});
