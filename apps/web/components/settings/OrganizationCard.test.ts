import { describe, expect, it } from "vitest";
import { formatTerms, parseTerms } from "./OrganizationCard";

describe("organization terminology", () => {
  it("reads one 'avoid = use' pair per line and skips incomplete lines", () => {
    expect(parseTerms("mutasaddi = mas'ul\n  ijro = bajarish \nnoto'g'ri\n = bo'sh\nа=б=в")).toEqual({
      mutasaddi: "mas'ul",
      ijro: "bajarish",
      а: "б=в",
    });
  });

  it("round-trips the saved dictionary", () => {
    const terms = { mutasaddi: "mas'ul", "ko'rib chiqish": "o'rganish" };
    expect(parseTerms(formatTerms(terms))).toEqual(terms);
    expect(formatTerms(undefined)).toBe("");
  });
});
