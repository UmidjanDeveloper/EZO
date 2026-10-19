import { describe, expect, it } from "vitest";
import { careerLines, parseCareerLines } from "./career-lines";

describe("career profile lines", () => {
  it("parses entries and round-trips them", () => {
    const lines = {
      experience: "Tahlilchi | Vazirlik | 2021 | | Vaqtni 30% qisqartirdim; Hisobot tizimi\n\n",
      education: "TATU | Bakalavr | Informatika | 2016 | 2020",
      skills: "Python, SQL,\nPower BI",
      languages: "Ingliz tili | B2",
      certificates: "Google Data Analytics | Google | 2022",
    };
    const parsed = parseCareerLines(lines);
    expect(parsed.experience).toEqual([
      {
        role: "Tahlilchi",
        organization: "Vazirlik",
        start: "2021",
        end: "",
        achievements: ["Vaqtni 30% qisqartirdim", "Hisobot tizimi"],
      },
    ]);
    expect(parsed.skills).toEqual(["Python", "SQL", "Power BI"]);
    expect(parsed.languages).toEqual([{ language: "Ingliz tili", level: "B2" }]);
    const back = careerLines({ full_name: "D", ...parsed });
    expect(back.experience).toBe("Tahlilchi | Vazirlik | 2021 |  | Vaqtni 30% qisqartirdim; Hisobot tizimi");
    expect(back.languages).toBe("Ingliz tili | B2");
    expect(careerLines(null).skills).toBe("");
  });
});
