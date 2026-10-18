# ruff: noqa: E501  (style rules and phrase lists are kept on one line each)
"""Writing modes, the options a user can set in words, and a deterministic style check.

The style check (`lint`) needs no model. It finds the usual weaknesses of machine-written
Uzbek: empty openers and closers, inflated praise, repeated phrases, mixed Latin/Cyrillic
script, overlong sentences, and claims that a document was signed or approved.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from ezo_api.core.text import normalize

MODES: dict[str, str] = {
    "natural": "Clear, natural, human writing: plain words, varied sentence length, no filler.",
    "official": "Official administrative Uzbek (rasmiy-idoraviy uslub): precise, neutral, impersonal where customary, standard terms of Uzbekistan's public administration, no emotion or praise.",
    "academic": "Academic style: precise terms, cautious claims, logical structure, sources cited; no invented findings, data or references.",
    "business": "Business style: clear value, concrete terms, polite and direct.",
    "journalistic": "News style: the key fact first (who, what, when, where), then details; neutral; quotes only if supplied.",
    "pr": "Public-relations style: positive but factual; no superlatives the facts do not support.",
    "persuasive": "Persuasive: a clear claim, reasons and evidence from the given facts, a call to action.",
    "concise": "Concise: short sentences, only what is needed, lists where they help.",
    "formal_letter": "Formal correspondence: courteous, structured, respectful address.",
    "friendly": "Warm and friendly, still correct and respectful.",
    "technical": "Technical: exact terms, steps and parameters, unambiguous.",
    "legal_drafting": "Legal drafting assistance: numbered provisions, defined terms, no invented legal grounds, article numbers or document numbers (use placeholders).",
    "speech": "Spoken style: short sentences, direct address to the audience, clear signposting, easy to read aloud.",
    "editing": "Editing: keep the author's meaning and facts; fix language, structure and clarity.",
}

_MODE_WORDS: list[tuple[str, str]] = [
    (r"\b(ilmiy|akademik|academic|научн)", "academic"),
    (r"\b(rasmiy|official|официальн|расмий)", "official"),
    (r"\b(biznes|business|делов)", "business"),
    (r"\b(jurnalist|yangilik uslub|news style|журналист)", "journalistic"),
    (r"\b(ishontiruvchi|persuasive|убедительн)", "persuasive"),
    (r"\b(samimiy|do'stona|friendly|дружелюбн|тёпл|тепл)", "friendly"),
    (r"\b(texnik|technical|техническ)", "technical"),
    (r"\b(oddiy tilda|sodda|tabiiy|natural|простым языком|естественн)", "natural"),
]
_LENGTH: list[tuple[str, tuple[int, int]]] = [
    (r"\b(juda qisqa|very short|очень коротк)", (40, 120)),
    (r"\b(qisqa|qisqacha|short|brief|кратк|коротк)", (80, 250)),
    (r"\b(batafsil|to'liq|detailed|long|подробн|развернут)", (500, 1500)),
]
_WORDS_N = re.compile(r"\b(\d{2,4})\s*(so'z|words?|слов)")
_PAGES_N = re.compile(r"\b(\d{1,2})\s*(bet|sahifa|pages?|страниц)\w*")
_LANG: list[tuple[str, str]] = [
    (r"\b(kirill\w*|kirillcha|кирилл\w*|cyrillic)", "uz-cyrl"),
    (r"\b(ruscha|rus tilida|по-русски|на русском|in russian)", "ru"),
    (r"\b(inglizcha|ingliz tilida|in english|на английском)", "en"),
    (r"\b(o'zbekcha|lotin\w*|in uzbek|на узбекском)", "uz"),
]


@dataclass(slots=True)
class Options:
    mode: str | None = None
    words: tuple[int, int] | None = None
    language: str | None = None
    """uz | uz-cyrl | ru | en (None: the conversation's language)."""
    audience: str | None = None
    draft_label: bool = True


def options_from(text: str) -> Options:
    """What the user said about tone, length, language and the draft label."""
    norm = normalize(text)
    options = Options()
    options.mode = next((mode for pattern, mode in _MODE_WORDS if re.search(pattern, norm)), None)
    if match := _WORDS_N.search(norm):
        n = int(match.group(1))
        options.words = (max(20, int(n * 0.85)), int(n * 1.15))
    elif match := _PAGES_N.search(norm):
        n = int(match.group(1))
        options.words = (n * 300, n * 450)
    else:
        options.words = next((w for pattern, w in _LENGTH if re.search(pattern, norm)), None)
    options.language = next((lang for pattern, lang in _LANG if re.search(pattern, norm)), None)
    if audience := re.search(
        r"\b(talabalar|o'quvchilar|rahbariyat|xodimlar|fuqarolar|ota-onalar|students|teachers|citizens)\b",
        norm,
    ):
        options.audience = audience.group(1)
    if re.search(
        r"\b(qoralama belgisisiz|loyiha belgisisiz|without (the )?draft (label|mark)|без пометки)",
        norm,
    ):
        options.draft_label = False
    return options


UZBEK_STYLE_RULES = """Uzbek quality rules:
- Write the way a skilled Uzbek civil servant, editor or teacher writes: clear, natural, correct. Use o‘ and g‘ consistently (or o' g' if the user writes so); never mix Latin and Cyrillic in one text.
- Do not open with empty phrases ("Hozirgi kunda", "Bugungi kunda dolzarb", "Ma'lumki", "Shuni alohida ta'kidlash joizki") or close with generic slogans. Start with the point.
- No inflated praise ("ulug'vor", "beqiyos", "misli ko'rilmagan", "tarixiy ahamiyatga molik") unless the user wrote it.
- No repeated phrases; vary sentence length; one idea per sentence in official text.
- Use the standard terms of Uzbekistan's administration (hokimlik, hokim o'rinbosari, idora, ijro intizomi, murojaat, ma'lumot uchun, ilova…), not calques from Russian or English.
- Never invent names, positions, dates, numbers, document numbers, legal grounds, quotes or statistics. Put a placeholder in square brackets, e.g. [Qabul qiluvchi], [sana], for anything not given.
- Never write that the document is signed, approved, registered or sealed; signature and seal places stay as placeholders ([imzo], [M.O.])."""

_CLICHES = [
    "hozirgi kunda",
    "bugungi kunda dolzarb",
    "shuni alohida ta'kidlash joizki",
    "ma'lumki,",
    "shuni ta'kidlash kerakki",
    "xulosa qilib aytganda",
    "bugungi globallashuv davrida",
    "zamon talabi",
    "yuksak darajada",
    "keng ko'lamli islohotlar doirasida",
    "в настоящее время",
    "необходимо отметить, что",
    "in today's fast-paced world",
    "it is worth noting that",
    "in conclusion,",
]
_PRAISE = [
    "ulug'vor",
    "beqiyos",
    "misli ko'rilmagan",
    "tarixiy ahamiyatga molik",
    "betakror",
    "eng buyuk",
    "unprecedented",
    "groundbreaking",
    "беспрецедентн",
]
_CLAIMS = re.compile(
    r"\b(imzolandi|imzolangan|tasdiqlandi|muhr bosildi|ro'yxatdan o'tkazildi|"
    r"подписан[оа]?|утвержден[оа]?|заверен[оа]? печатью|signed by|has been approved|stamped)\b"
)
_SENTENCE = re.compile(r"(?<=[.!?])\s+")


@dataclass(slots=True)
class StyleIssue:
    kind: str
    detail: str


@dataclass(slots=True)
class StyleReport:
    issues: list[StyleIssue] = field(default_factory=list)

    def by_kind(self, kind: str) -> list[StyleIssue]:
        return [i for i in self.issues if i.kind == kind]

    def summary(self) -> list[str]:
        return [f"{i.kind}: {i.detail}" for i in self.issues[:20]]


def lint(text: str) -> StyleReport:
    report = StyleReport()
    norm = normalize(text)
    for phrase in _CLICHES:
        if phrase in norm:
            report.issues.append(StyleIssue("cliche", phrase))
    for word in _PRAISE:
        if word in norm:
            report.issues.append(StyleIssue("inflated", word))
    for match in _CLAIMS.finditer(norm):
        report.issues.append(StyleIssue("approval_claim", match.group(0)))
    latin = len(re.findall(r"[a-z]", norm))
    cyrillic = len(re.findall(r"[а-яёўқғҳ]", norm))
    if latin > 40 and cyrillic > 40:
        report.issues.append(
            StyleIssue("mixed_script", f"{latin} Latin and {cyrillic} Cyrillic letters")
        )
    words = re.findall(r"[\w'‘’ʻ-]+", norm)
    grams = Counter(" ".join(words[i : i + 4]) for i in range(len(words) - 3))
    for gram, count in grams.most_common(3):
        if count >= 3 and not re.fullmatch(r"[\d\s.-]+", gram):
            report.issues.append(StyleIssue("repetition", f"“{gram}” ×{count}"))
    for sentence in _SENTENCE.split(text):
        if len(sentence.split()) > 45:
            report.issues.append(StyleIssue("long_sentence", sentence[:80] + "…"))
            break
    return report
