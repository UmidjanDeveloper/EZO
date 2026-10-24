/**
 * Turns what the USER said or typed into one of a few registered desktop actions.
 *
 * Only the user's own words are parsed here — never a model reply — and every result
 * maps to a fixed, reviewed implementation in actions.ts. Anything else is a normal
 * conversation sent to the EZO API. There is no path from text to a shell command.
 */

export type AppId = "calculator" | "notepad" | "paint" | "explorer";
export type VolumeChange = "up" | "down" | "mute";

export type Intent =
  | { kind: "open_app"; app: AppId }
  | { kind: "volume"; change: VolumeChange }
  | { kind: "find_file"; query: string }
  | { kind: "open_file"; query: string }
  | { kind: "open_result"; index: number }
  | { kind: "dictate"; text: string }
  | { kind: "explain_screen"; question: string }
  | { kind: "jarvis_task"; text: string }
  | { kind: "chat"; text: string };

// \p{L} instead of \w and look-behind instead of \b, so Cyrillic words match too.
const W = "\\p{L}*";
const word = (alternatives: string) => new RegExp(`(?<!\\p{L})(${alternatives})`, "u");
const APP_WORDS: [AppId, RegExp][] = [
  ["calculator", word(`kalkulyator${W}|calculator|hisoblagich${W}|калькулятор${W}`)],
  ["notepad", word(`bloknot${W}|notepad|блокнот${W}`)],
  ["paint", word(`paint|peynt${W}|rasm chiz${W}`)],
  ["explorer", word(`explorer|provodnik${W}|fayl menejer${W}|papkalar${W}|проводник${W}`)],
];
const OPEN_VERB = word(`och${W}|ishga tushir${W}|open|launch|start|откр${W}|запуст${W}`);
const ORDINALS: Record<string, number> = {
  birinchi: 0,
  "1": 0,
  ikkinchi: 1,
  "2": 1,
  uchinchi: 2,
  "3": 2,
  first: 0,
  second: 1,
  third: 2,
};

/** Lowercase, unify the many apostrophes Uzbek Latin is typed with, squeeze spaces. */
export function normalize(text: string): string {
  return text
    .normalize("NFC")
    .replace(/[‘’ʻʼ`´]/g, "'")
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase();
}

function cleanQuery(raw: string): string {
  return raw
    .replace(/["“”«»]/g, "")
    .replace(/\b(nomli|degan|called|named)\b/g, "")
    .replace(/[.!?,;:]+$/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

export function parseIntent(input: string): Intent {
  const original = input.trim().replace(/\s+/g, " ");
  const text = normalize(original);

  // Dictation keeps the user's original casing and punctuation after the marker.
  const dictate = /^(yoz(ib ber)?|yozing|type|напиши)\s*[:\-–]\s*/i.exec(original);
  if (dictate) {
    const body = original.slice(dictate[0].length).trim();
    if (body) return { kind: "dictate", text: body };
  }

  // A governed multi-step task on the authorised Downloads folder (validated by the server).
  if (/(downloads?|yuklab olingan|загрузк)/.test(text) && /(pdf|telegram|телеграм|foiz|percent|процент)/.test(text)) {
    return { kind: "jarvis_task", text: original };
  }

  if (word(`ekran${W}|screen|экран${W}`).test(text) && /(tushuntir|nima|ko'r|o'qi|explain|what|tahlil|объясн|что)/.test(text)) {
    return { kind: "explain_screen", question: original };
  }

  if (word(`ovoz${W}|volume|громк${W}`).test(text)) {
    if (/(o'chir|jim|mute|выключ)/.test(text)) return { kind: "volume", change: "mute" };
    if (/(baland|ko'tar|oshir|kuchaytir|up|louder|громче|увелич)/.test(text)) return { kind: "volume", change: "up" };
    if (/(past|pasaytir|kamaytir|down|quieter|тише|уменьш)/.test(text)) return { kind: "volume", change: "down" };
  }

  const nth = /^(birinchi|ikkinchi|uchinchi|first|second|third|[123])\w*\s+(\w+\s+)?(och\w*|open)/.exec(text);
  if (nth) {
    const index = ORDINALS[nth[1] ?? ""];
    if (index !== undefined) return { kind: "open_result", index };
  }

  const fileFind = /^(.+?)\s+(fayl\w*|hujjat\w*)\s*(ni|ini)?\s*(top|qidir|izla)\w*/.exec(text)
    ?? /^(?:find|search(?: for)?)\s+(?:the\s+)?(?:file\s+)?(.+?)(?:\s+file)?$/.exec(text);
  if (fileFind) {
    const query = cleanQuery((fileFind[1] ?? "").replace(/\b(menga|iltimos|please)\b/g, ""));
    if (query) return { kind: "find_file", query };
  }
  const fileOpen = /^(.+?)\s+(fayl\w*|hujjat\w*)\s*(ni|ini)?\s*(och\w*)/.exec(text);
  if (fileOpen) {
    const query = cleanQuery((fileOpen[1] ?? "").replace(/\b(menga|iltimos)\b/g, ""));
    if (query) return { kind: "open_file", query };
  }

  if (OPEN_VERB.test(text)) {
    for (const [app, pattern] of APP_WORDS) if (pattern.test(text)) return { kind: "open_app", app };
  }

  return { kind: "chat", text: original };
}
