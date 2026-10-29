import type { LanguageCode } from "@ezo/shared";

/**
 * Spoken interpreter mode: "EZO, menga tarjimon bo'lib ber" turns the voice stage into an
 * interpreter between two people. Pure helpers only (the stage does the listening/speaking).
 */
export type LanguagePair = readonly [LanguageCode, LanguageCode];
export type InterpreterCommand = { kind: "start"; pair: LanguagePair } | { kind: "stop" } | null;

const normalize = (text: string) =>
  text
    .toLowerCase()
    .replace(/[‘’ʻʼ`´]/g, "'")
    .replace(/\s+/g, " ")
    .trim();

const START = /tarjimon|tarjimonlik|tarjima qilib (tur|ber)|interpreter|translator|переводчик|переводи(ть)? (нам|между)/;
const STOP =
  /(tarjimon\w*|tarjima\w*) (rejimi\w* )?(to'xta\w*|tugat\w*|o'chir\w*|yetarli|kerak emas)|(stop|end|exit|turn off) (the )?(interpret\w*|translat\w*)|(хватит|стоп|выключи|останови)\w* (перевод\w*)|переводчик\w* (не нужен|выключи)/;

const NAMES: [LanguageCode, RegExp][] = [
  ["uz", /o'?zbek|uzbek|узбек/],
  ["en", /ingliz|english|англи/],
  ["ru", /\brus(cha|ch|sian)?\b|russian|русск|по-русски/],
];

/** Languages named in the text, in the order they are mentioned. */
function namedLanguages(text: string): LanguageCode[] {
  return NAMES.map(([code, pattern]) => [code, text.search(pattern)] as const)
    .filter(([, at]) => at >= 0)
    .sort((a, b) => a[1] - b[1])
    .map(([code]) => code);
}

/**
 * Reads a spoken command. Two named languages are the pair; one named language is paired with
 * the language the command was spoken in (or Uzbek); none means the speaker's language ⇄ English
 * (Uzbek ⇄ English when the speaker spoke English or nothing is known).
 */
export function parseInterpreterCommand(text: string, spoken: LanguageCode | null = null): InterpreterCommand {
  const said = normalize(text);
  if (STOP.test(said)) return { kind: "stop" };
  if (!START.test(said)) return null;
  const named = namedLanguages(said);
  const home: LanguageCode = spoken ?? "uz";
  if (named.length >= 2) return { kind: "start", pair: [named[0]!, named[1]!] };
  if (named.length === 1) {
    const other = named[0]!;
    const first = other === home ? (home === "uz" ? "en" : "uz") : home;
    return { kind: "start", pair: [first, other] };
  }
  return { kind: "start", pair: home === "en" ? ["uz", "en"] : [home, "en"] };
}

/** The language to translate into: the other side of the pair from what was spoken. */
export function otherSide(pair: LanguagePair, spoken: LanguageCode): LanguageCode {
  return spoken === pair[0] ? pair[1] : pair[0];
}

/** Which side spoke: the recognised language when it is one of the pair, else the side expected. */
export function speakerSide(pair: LanguagePair, recognised: LanguageCode | null, expected: LanguageCode): LanguageCode {
  return recognised && pair.includes(recognised) ? recognised : expected;
}
