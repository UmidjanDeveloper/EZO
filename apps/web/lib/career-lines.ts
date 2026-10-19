import type { CareerProfile } from "@ezo/shared";

/**
 * The career profile edited as plain lines (one entry per line, fields separated by "|"),
 * so it can be typed or pasted without a complex form:
 *   experience:   Lavozim | Tashkilot | Boshlanish | Tugash | yutuq; yutuq
 *   education:    Muassasa | Daraja | Yo'nalish | Boshlanish | Tugash
 *   languages:    Til | Daraja
 *   certificates: Nomi | Beruvchi | Yil
 */
export interface CareerLines {
  experience: string;
  education: string;
  skills: string;
  languages: string;
  certificates: string;
}

function rows(text: string): string[][] {
  return text
    .split("\n")
    .map((line) => line.split("|").map((part) => part.trim()))
    .filter((parts) => parts[0]);
}

export function parseCareerLines(lines: CareerLines): Pick<
  CareerProfile,
  "experience" | "education" | "skills" | "languages" | "certificates"
> {
  return {
    experience: rows(lines.experience).map(([role, organization = "", start = "", end = "", achievements = ""]) => ({
      role,
      organization,
      start,
      end,
      achievements: achievements
        .split(";")
        .map((item) => item.trim())
        .filter(Boolean),
    })),
    education: rows(lines.education).map(([institution, degree = "", field = "", start = "", end = ""]) => ({
      institution,
      degree,
      field,
      start,
      end,
    })),
    skills: lines.skills
      .split(/[,\n]/)
      .map((skill) => skill.trim())
      .filter(Boolean),
    languages: rows(lines.languages).map(([language, level = ""]) => ({ language, level })),
    certificates: rows(lines.certificates).map(([name, issuer = "", year = ""]) => ({ name, issuer, year })),
  };
}

function join(parts: (string | undefined)[]): string {
  const values = parts.map((part) => part ?? "");
  while (values.length > 1 && !values[values.length - 1]) values.pop();
  return values.join(" | ");
}

export function careerLines(profile: CareerProfile | null): CareerLines {
  return {
    experience: (profile?.experience ?? [])
      .map((e) => join([e.role, e.organization, e.start, e.end, (e.achievements ?? []).join("; ")]))
      .join("\n"),
    education: (profile?.education ?? []).map((e) => join([e.institution, e.degree, e.field, e.start, e.end])).join("\n"),
    skills: (profile?.skills ?? []).join(", "),
    languages: (profile?.languages ?? []).map((l) => join([l.language, l.level])).join("\n"),
    certificates: (profile?.certificates ?? []).map((c) => join([c.name, c.issuer, c.year])).join("\n"),
  };
}
